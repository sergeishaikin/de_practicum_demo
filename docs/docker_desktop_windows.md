# Docker Desktop for Windows

Минимальная справка для demo-стенда. Это не замена официальной документации Docker.

Официальные страницы:

- Docker Desktop Windows install: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker account: https://docs.docker.com/accounts/create-account/

## Что установить

Скачай Docker Desktop for Windows с официального сайта Docker и установи обычным мастером.

При первом запуске Docker может попросить вход в аккаунт. Это нормально. Для demo тебе нужен только доступ к Docker Desktop и скачиванию образов, публиковать образы не нужно.

## WSL

На Windows Docker Desktop обычно работает через WSL 2.

Если видишь сообщение вроде `WSL needs updating`, не продолжай запуск стенда. Сначала обнови WSL:

```powershell
wsl --update
```

Команду лучше выполнять в PowerShell от имени администратора. Потом перезапусти Docker Desktop.

## Проверка

В PowerShell:

```powershell
docker --version
docker compose version
docker run hello-world
```

Если первые две команды работают, Docker CLI установлен. Если `hello-world` скачался и запустился, Docker engine реально живой.

## Типовые ошибки

`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`

Docker Desktop не запущен или engine еще не поднялся.

`Access is denied`

Часто помогает перезапустить Docker Desktop. Если не помогло, проверь права пользователя и группу `docker-users`.

`EOF` при скачивании образа

Это сбой сети, Docker Hub, VPN, прокси или корпоративного фильтра. Повтори позже, смени сеть/VPN или используй локальный compose:

```powershell
docker compose -f docker-compose.local-airflow.yml up -d
```

Этот вариант работает только если локальный образ `local/airflow:2.9.3-lab` уже есть на машине.
