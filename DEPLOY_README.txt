ECHOES OF THE RIFT — CABINS 2.0 + CORE/UX DEPLOY

Перед загрузкой в BotHost:
1) Распакуйте архив поверх корня вашего GitHub-репозитория.
2) НЕ удаляйте существующий database.db. В этом архиве database.db намеренно отсутствует.
3) Не заменяйте свой data/attachment_cache.json — он также намеренно не включён.
4) В BotHost добавьте обязательную переменную:
   BOT_OWNER_ID=ВАШ_ЧИСЛОВОЙ_VK_ID
5) Проверьте VK_TOKEN/BOT_TOKEN и ADMIN_CHAT_ID.
6) Commit -> Push origin в GitHub Desktop, затем дождитесь деплоя BotHost.
7) После запуска проверьте логи и выполните короткий smoke-test из BOTHOST_SETUP.txt.

Миграции новых таблиц/полей выполняются автоматически при запуске.
