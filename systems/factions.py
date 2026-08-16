def register_factions_handlers(bot, deps):
    sci_line = deps["sci_line"]
    main_menu = deps["main_menu"]
    FACTION_DESCRIPTIONS = deps["FACTION_DESCRIPTIONS"]
    FACTION_ARTS = deps["FACTION_ARTS"]
    stabilize_attachments = deps["stabilize_attachments"]

    @bot.on.message(text="🏛 Фракции")
    async def factions_handler(message):
        await message.answer(
            "◢ ФРАКЦИОННЫЙ РЕЕСТР ◣\n"
            f"{sci_line()}\n\n"
            "Доступные организации мира Echoes of the Rift.\n"
            "Фракция выбирается при создании квенты.",
            keyboard=main_menu.get_json()
        )

        for faction_name, faction_desc in FACTION_DESCRIPTIONS.items():
            if faction_name == "🚫 Без фракции":
                continue

            art = FACTION_ARTS.get(faction_name)
            stable_art = await stabilize_attachments(bot, art, message.peer_id) if art else None
            await message.answer(
                f"{faction_name}\n\n{faction_desc}",
                attachment=stable_art or art
            )

        await message.answer(
            "🚫 Без фракции\n\n"
            f"{FACTION_DESCRIPTIONS['🚫 Без фракции']}",
            keyboard=main_menu.get_json()
        )

