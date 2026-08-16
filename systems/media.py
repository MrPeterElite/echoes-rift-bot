import asyncio
import json
import urllib.request
from pathlib import Path

from vkbottle import PhotoMessageUploader


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_PATH = _PROJECT_ROOT / "data" / "attachment_cache.json"
_CACHE_LOCK = asyncio.Lock()
_HISTORY_PAGE_SIZE = 200
_HISTORY_MAX_PAGES = 25
_FAILED = set()


def _load_cache():
    try:
        if _CACHE_PATH.exists():
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"[media] Не удалось прочитать кэш вложений: {exc!r}")
    return {}


_ATTACHMENT_CACHE = _load_cache()


def _save_cache_sync(cache):
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _CACHE_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(_CACHE_PATH)


async def _remember(source, stable):
    async with _CACHE_LOCK:
        _ATTACHMENT_CACHE[source] = stable
        await asyncio.to_thread(_save_cache_sync, dict(_ATTACHMENT_CACHE))


def _split_attachments(attachment):
    if not attachment:
        return []
    if isinstance(attachment, (list, tuple, set)):
        values = []
        for part in attachment:
            values.extend(_split_attachments(part))
        return values
    return [part.strip() for part in str(attachment).split(",") if part.strip()]


def _to_plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _extract_response(raw):
    raw = _to_plain(raw)
    if isinstance(raw, dict) and "response" in raw:
        return _to_plain(raw["response"])
    return raw


def _parse_photo_attachment(attachment):
    if not isinstance(attachment, str) or not attachment.startswith("photo"):
        return None

    parts = attachment[5:].split("_")
    if len(parts) < 2:
        return None

    try:
        owner_id = int(parts[0])
        photo_id = int(parts[1])
    except ValueError:
        return None

    access_key = parts[2] if len(parts) >= 3 else None
    return owner_id, photo_id, access_key


def _photo_url_from_object(photo):
    photo = _to_plain(photo)
    if not isinstance(photo, dict):
        return None

    sizes = photo.get("sizes") or []
    normalized = []
    for size in sizes:
        size = _to_plain(size)
        if isinstance(size, dict) and size.get("url"):
            normalized.append(size)

    if normalized:
        best = max(
            normalized,
            key=lambda item: (item.get("width", 0) or 0) * (item.get("height", 0) or 0),
        )
        return best.get("url")

    return photo.get("orig_photo", {}).get("url") if isinstance(photo.get("orig_photo"), dict) else (
        photo.get("url") or photo.get("src_xxbig") or photo.get("src_big")
    )


def _history_attachment_photo(item):
    item = _to_plain(item)
    if not isinstance(item, dict):
        return None

    attachment = _to_plain(item.get("attachment"))
    if not isinstance(attachment, dict):
        return None

    photo = attachment.get("photo")
    if photo is None and attachment.get("type") == "photo":
        photo = attachment.get("photo") or attachment.get("object")

    return _to_plain(photo)


async def _find_photo_in_dialog_history(bot, peer_id, target_owner_id, target_photo_id):
    """Ищет исходное фото в истории вложений диалога сообщества.

    В отличие от photos.getById, messages.getHistoryAttachments относится к
    сообщениям самого сообщества и доступен при авторизации токеном группы.
    Это позволяет восстановить старые фото, которые игрок/админ когда-то уже
    присылал боту.
    """
    start_from = None

    for _ in range(_HISTORY_MAX_PAGES):
        params = {
            "peer_id": int(peer_id),
            "media_type": "photo",
            "count": _HISTORY_PAGE_SIZE,
        }
        if start_from:
            params["start_from"] = start_from

        raw = await bot.api.request("messages.getHistoryAttachments", params)
        payload = _extract_response(raw)
        payload = _to_plain(payload)

        if not isinstance(payload, dict):
            return None

        items = payload.get("items") or []
        for item in items:
            photo = _history_attachment_photo(item)
            if not isinstance(photo, dict):
                continue

            try:
                owner_id = int(photo.get("owner_id"))
                photo_id = int(photo.get("id"))
            except (TypeError, ValueError):
                continue

            if owner_id == target_owner_id and photo_id == target_photo_id:
                return _photo_url_from_object(photo)

        next_from = payload.get("next_from")
        if not next_from or next_from == start_from:
            break
        start_from = next_from

    return None


async def _resolve_photo_url(bot, attachment, current_peer_id=None):
    parsed = _parse_photo_attachment(attachment)
    if not parsed:
        return None

    owner_id, photo_id, _access_key = parsed

    # Главный вариант: фото уже присылалось этому сообществу. Для пользовательских
    # фото owner_id одновременно является ID диалога пользователя с ботом.
    candidate_peers = []
    if owner_id > 0:
        candidate_peers.append(owner_id)

    # Для свежих вложений полезен и текущий peer_id (например, если owner_id фото
    # отличается от отправителя из-за пересылки/альбома).
    if current_peer_id and int(current_peer_id) < 2_000_000_000:
        current_peer_id = int(current_peer_id)
        if current_peer_id not in candidate_peers:
            candidate_peers.append(current_peer_id)

    last_exc = None
    for peer_id in candidate_peers:
        try:
            url = await _find_photo_in_dialog_history(bot, peer_id, owner_id, photo_id)
            if url:
                return url
        except Exception as exc:
            last_exc = exc

    if last_exc:
        raise last_exc
    return None


def _download_bytes_sync(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 EchoesRiftBot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


async def _upload_local_photo(bot, local_file, peer_id):
    path = (_PROJECT_ROOT / str(local_file)).resolve()
    try:
        path.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError("локальный путь выходит за пределы проекта") from exc

    if not path.is_file():
        raise RuntimeError(f"локальный файл не найден: {local_file}")

    uploader = PhotoMessageUploader(bot.api)
    stable = await uploader.upload(file_source=str(path), peer_id=peer_id)
    if isinstance(stable, (list, tuple)):
        stable = ",".join(str(item) for item in stable if item)
    stable = str(stable).strip()
    if not stable:
        raise RuntimeError("VK не вернул вложение после загрузки локального файла")
    return stable


async def _reupload_photo(bot, source_attachment, peer_id, history_peer_id=None):
    url = await _resolve_photo_url(
        bot,
        source_attachment,
        current_peer_id=history_peer_id or peer_id,
    )
    if not url:
        raise RuntimeError(
            "фото не найдено в истории сообщений сообщества; "
            "его нужно один раз повторно прислать боту"
        )

    image_bytes = await asyncio.to_thread(_download_bytes_sync, url)
    if not image_bytes:
        raise RuntimeError("получен пустой файл фотографии")

    uploader = PhotoMessageUploader(bot.api)
    stable = await uploader.upload(
        file_source=image_bytes,
        peer_id=peer_id,
    )

    if isinstance(stable, (list, tuple)):
        stable = ",".join(str(item) for item in stable if item)
    stable = str(stable).strip()

    if not stable:
        raise RuntimeError("VK не вернул новое вложение после загрузки")

    return stable


async def stabilize_attachments(bot, attachment, peer_id, local_file=None, history_peer_id=None):
    """Перезаливает старые photo-вложения в сообщения сообщества и кэширует ID.

    Важно: photos.getById здесь намеренно НЕ используется. Этот метод недоступен
    с токеном сообщества и вызывает VKAPIError_27. Вместо него исходное фото
    ищется в истории вложений диалога, куда оно было прислано игроком/админом.
    """
    sources = _split_attachments(attachment)
    if not sources:
        return None

    result = []
    for source in sources:
        cached = _ATTACHMENT_CACHE.get(source)
        if cached:
            result.append(cached)
            continue

        if not source.startswith("photo"):
            result.append(source)
            continue

        # Фото, уже принадлежащее сообществу, повторно загружать не нужно.
        parsed = _parse_photo_attachment(source)
        if parsed and parsed[0] < 0:
            result.append(source)
            continue

        try:
            if local_file and len(sources) == 1:
                stable = await _upload_local_photo(bot, local_file, peer_id)
                print(f"[media] Локальный резерв загружен: {local_file}")
            else:
                stable = await _reupload_photo(bot, source, peer_id, history_peer_id=history_peer_id)
            await _remember(source, stable)
            _FAILED.discard(source)
            result.append(stable)
            print(f"[media] Вложение восстановлено: {source} -> {stable}")
        except Exception as exc:
            # Не засоряем консоль одной и той же ошибкой при листании магазина.
            if source not in _FAILED:
                print(f"[media] Не удалось восстановить {source}: {exc!r}")
                _FAILED.add(source)
            result.append(source)

    return ",".join(result) if result else None
