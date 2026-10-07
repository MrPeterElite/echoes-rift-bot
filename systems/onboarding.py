"""Registration-only entry screens and a gate before player handlers."""
from vkbottle import BaseMiddleware
import database as db
from systems.navigation import MAIN_MENU,menu

CREATE='👤 Создать персонажа'
CONTINUE='✏️ Продолжить создание'
STATUS='⏳ Статус персонажа'
HELP='❓ Помощь'
HOME={'/старт','/start','Начать','начать','🏠 Главное меню','⬅️ Назад',STATUS}
HELP_LABELS={HELP,'/помощь','/команды','📖 Как играть'}
DELETE_LABELS={'🗑 Удалить персонажа','🗑 Подтвердить удаление персонажа','↩ Отменить удаление персонажа'}

async def entry(uid):
    c=await db.get_character_by_user(uid)
    if c and c[10]=='approved':return 'Выберите раздел.',MAIN_MENU
    if c:
        if c[10]=='rejected':
            return (f'Персонаж «{c[2]}» отклонён. Игровые разделы пока закрыты.\nЧтобы создать другого персонажа, удалите отклонённого с подтверждением.',menu([[STATUS],['🗑 Удалить персонажа'],[HELP]]))
        return (f'⏳ Персонаж «{c[2]}» ожидает проверки.\nПосле одобрения откроются игровые разделы.',menu([[STATUS],[HELP]]))
    draft=await db.load_character_draft(uid)
    if draft:return 'Создание персонажа сохранено. Можно продолжить с того же шага.',menu([[CONTINUE],[HELP]])
    return 'Добро пожаловать! Создайте персонажа. После одобрения откроется игра.',menu([[CREATE],[HELP]])

async def entry_keyboard(uid):return (await entry(uid))[1].get_json()

async def show_entry(message):
    text,kb=await entry(message.from_id)
    await message.answer(text,keyboard=kb.get_json())

def install_onboarding(bot,admin_chat,runtime,faction_labels,control_labels):
    @bot.on.message(text=[STATUS,HELP])
    async def onboarding_status(message):
        if message.peer_id!=message.from_id:
            await message.answer('Статус персонажа доступен в ЛС бота.');return
        await show_entry(message)

    async def intercept(message):
        uid=message.from_id;text=(message.text or '').strip()
        c=await db.get_character_by_user(uid)
        if c and c[10]=='approved':return False
        if message.peer_id==admin_chat:
            admin=await db.get_bot_admin(uid)
            if admin and admin[2]:return False
        if message.peer_id!=uid:
            if text.startswith('/') or getattr(message,'payload',None):
                await message.answer('Игровые действия откроются после одобрения персонажа. Создание — в ЛС бота.')
            return True
        if text in HOME:
            await runtime['pause_draft'](message);await show_entry(message);return True
        if text in HELP_LABELS:
            await runtime['pause_draft'](message)
            await message.answer('Создайте персонажа: имя, возраст, пол, фракция, биология, характер, история и хотя бы один арт.\nЧерновик сохраняется. Кнопка «Готово» отправит его на проверку. До одобрения игровые разделы закрыты.',keyboard=await entry_keyboard(uid));return True
        if c:
            if c[10]=='rejected' and text in DELETE_LABELS:return False
            await show_entry(message);return True
        if text in {CREATE,CONTINUE,'📜 Создать квенту','📜 Создать персонажа'}:
            await runtime['create'](message);return True
        draft=await db.load_character_draft(uid)
        if draft and draft.get('active',True):
            if text in {'✅ Готово','🔄 Начать заново',*faction_labels}:return False
            if not text.startswith('/') and text not in control_labels:
                await runtime['handle_message'](message);return True
        await show_entry(message);return True

    class OnboardingMiddleware(BaseMiddleware):
        async def pre(self):
            if await intercept(self.event):self.stop('registration gate')
    bot.labeler.message_view.register_middleware(OnboardingMiddleware)
    return intercept
