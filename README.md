# PostgreSQL Orchestrator

## О проекте

PostgreSQL Orchestrator — это инструмент автоматизации управления базами данных PostgreSQL. Основная цель проекта — упростить сценарии обновлений и тестирования производительности с помощью Docker и YAML-конфигураций.

Современные базы данных являются неотъемлемой частью любого высоконагруженного приложения. Эффективное управление обновлениями и производительностью является важным фактором обеспечения стабильности и высокой доступности системы. 

PostgreSQL Orchestrator позволяет:
- Автоматизировать обновление баз данных, включая сложные сценарии с использованием `pg_upgrade`, minor обновления и создание резервных копий через `pg_dumpall`.
- Тестировать производительность баз данных, анализировать планы выполнения запросов (EXPLAIN) и измерять время выполнения запросов в разных условиях.
- Использовать YAML-манифесты для четкого описания конфигураций и сценариев.
- Управлять Docker-контейнерами для упрощения настройки и изоляции тестовой среды.

Проект состоит из двух ключевых модулей:

1. **Upgrade модуль**: Автоматизирует сценарии обновления баз данных. Поддерживает обновления с использованием `pg_upgrade`, minor обновления и создание полных дампов баз данных.
2. **Performance модуль**: Автоматизирует тестирование производительности баз данных, включая анализ планов выполнения запросов и измерение времени выполнения SQL-запросов.

В PostgreSQL Orchestrator поддерживаются два типа баз данных, каждый из которых имеет свои особенности:

- **ttdb**: Это СУБД Tantor — специализированное решение, разработанное компанией Tantor Labs. TantorDB расширяет функциональность PostgreSQL дополнительными возможностями для корпоративного использования. Дополнительную информацию и полную документацию по TantorDB можно найти по ссылке: [Документация TantorDB](https://docs.tantorlabs.ru/tdb/ru/16_8/be/intro-whatis.html).### Быстрый старт

- **pgdg**: Это официальный дистрибутив PostgreSQL, выпускаемый PostgreSQL Global Development Group (PGDG). Он устанавливается с использованием пакетов из репозитория PGDG и является стандартным выбором для большинства установок PostgreSQL. Подробную документацию по PostgreSQL можно прочитать на сайте: [Документация PostgreSQL](https://www.postgresql.org/docs/).Этот инструмент помогает командам DevOps, администраторам баз данных и разработчикам эффективно управлять PostgreSQL, снижая риск ошибок и экономя время.

Быстрый старт

#### Переменные окружения

При использовании базы данных типа `ttdb` необходимо задать следующие переменные окружения:

- **NEXUS_USER**: Имя пользователя для доступа к репозиторию Nexus.
  
- **NEXUS_USER_PASSWORD**: Пароль для доступа к репозиторию Nexus.
  
- **NEXUS_URL**: URL репозитория Nexus.
  

Пример установки переменных:

```shell
export NEXUS_USER='your_username'

export NEXUS_USER_PASSWORD='your_password'

export NEXUS_URL='public-nexus.tantrolabs.ru'
```

#### Особенности для релизов ttdb

Если вы работаете с релизами `ttdb`, в частности с бесплатным изданием `BE` (**Basic Edition**), можно указать значение `NEXUS_URL` равным `'public-nexus.tantrolabs.ru'`. Это означает, что дополнительная авторизация не требуется и вы можете использовать **BE**-издание без указания дополнительных учетных данных.

Тем не менее, для корректного формирования переменных окружения в сессии рекомендуется установить переменные `NEXUS_USER` и `NEXUS_USER_PASSWORD` (значения могут быть любыми, если они не используются непосредственно):

```shell
export NEXUS_USER='your_username'
export NEXUS_USER_PASSWORD='your_password'
```

Для баз данных типа `pgdg` указание переменных Nexus не требуется.

#### Настройка виртуального окружения Python
Для изоляции зависимостей рекомендуется использовать виртуальное окружение. Выполните следующие команды:

```sh
# Установка модуля для работы с виртуальными окружениями (если не установлен)
sudo apt install python3.10-venv

# Создание и активация виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей проекта
pip install -r requirements.txt

# Установка инструментов для тестирования
pip install pytest pytest-asyncio
```
#### Установка Docker (Ubuntu 22.04)

Для работы pg_orchestrator требуется Docker. 
Выполните следующие команды для установки Docker на Ubuntu 22.04:
```shell
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Добавление ключа GPG для Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление репозитория Docker
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io
```

Если при запуске pg_orchestrator возникает ошибка доступа к Docker daemon, выполните следующие команды:

```shell
sudo usermod -aG docker $USER
# После этого выйдите из сесси пользователя и войдите снова
```

#### Подготовка Docker-образа для тестов
Если вы хотите собрать Docker-образ, содержащий все необходимые зависимости для работы проекта, вы можете воспользоваться приведённым ниже Dockerfile. Это позволит создать изолированную среду для сборки и тестирования.

### Шаги для сборки образа

1. **Создайте Dockerfile**
  
  Сохраните следующий контент в файл с именем `Dockerfile` в корневой директории проекта:
  
  ```shell
  FROM ubuntu:22.04
  
  ARG DEBIAN_FRONTEND=noninteractive
  
  RUN apt-get update
  RUN apt-get install -y \
      jq git tree nano wget vim \
      build-essential cpanminus slapd ldap-utils libldap2-dev \
      autoconf bison clang-11 devscripts dpkg-dev flex \
      libldap2-dev libdbi-perl libgssapi-krb5-2 libicu-dev \
      krb5-kdc krb5-admin-server libssl-dev libpam0g-dev \
      libkrb5-dev krb5-user libcurl4-openssl-dev \
      perl perl-modules libipc-run-perl libtest-simple-perl libtime-hires-perl \
      liblz4-dev libpam-dev libreadline-dev libselinux1-dev libsystemd-dev \
      libxml2-dev libxslt-dev libzstd-dev llvm-11-dev locales-all pkg-config \
      python3-dev uuid-dev zlib1g-dev \
      openjade docbook-xml docbook-xsl opensp libxml2-utils xsltproc \
      libjson-perl curl time libgc-dev tcl-dev libperl-dev
  ```
  
2. **Соберите образ**
  
  Выполните следующую команду в терминале, находясь в директории с `Dockerfile`:
  
  ```shell
  docker build -t ubuntu:22.04 .
  ```
  
  Эта команда создаст Docker-образ с тегом `ubuntu:22.04`.
  
  После успешной сборки вы сможете использовать данный образ для дальнейшей разработки или тестирования проекта, запуская контейнеры с предустановленными зависимостями.

Если предпочитаете, вы можете заменить его на аналогичный Debian-подобный Docker-образ.
  
#### Запуск тестов и pg_orchestrator
Для проверки корректной работы инструмента выполните тесты:
```shell
pytest tests/*.py
```

### Параметры командной строки

Основной скрипт принимает следующие параметры командной строки:

- **--scenario**: Имя директории сценария внутри каталога `items/`. Этот параметр является обязательным и определяет сценарий, который должен быть выполнен. Если указано некорректное имя сценария, будет выведено сообщение с предложением списка доступных сценариев:
```sh
python pg_orchestrator.py --scenario=test
2025-01-18 01:12:57,141 - INFO - --- PG_ORCHESTRATOR VERSION: 1.0.0 ---
You must input the scenario name, example: ttdb_perf, pgdg_perf, pgdg_upgrade
```

Пример запуска PostgreSQL Orchestrator для сценария тестирования производительности:
```sh
python pg_orchestrator.py --scenario your_scenario_name
```

Для сценария тестирования обновления:
```sh
python pg_orchestrator.py --scenario upgrade_scenario_name
```
----------------
## Содержание

- [О проекте](#о-проекте)
- [Быстрый старт](#быстрый-старт)
- [Перед началом работы](#перед-началом-работы)
  - [Переменные окружения](#переменные-окружения)
  - [Параметры командной строки](#параметры-командной-строки)
- [Performance модуль](#performance-модуль)
  - [Структура директорий](#структура-директорий)
  - [Конфигурационный манифест (`conf.yaml`)](#конфигурационный-манифест-confyaml)
    - [Глобальные параметры](#глобальные-параметры)
    - [Тестовые кейсы](#тестовые-кейсы)
    - [Дополнительные параметры](#дополнительные-параметры)
    - [Пример использования performance_coefficient](#пример-использования-performance_coefficient)
    - [Пример timing_queries с дробным ожидаемым временем](#пример-timing_queries-с-дробным-ожидаемым-временем)
- [Upgrade модуль](#upgrade-модуль)
  - [Структура директорий](#структура-директорий-1)
  - [Конфигурационный манифест (`conf.yaml`)](#конфигурационный-манифест-confyaml-1)
    - [Глобальные параметры](#глобальные-параметры-1)
    - [Поля](#поля)
    - [Дополнительные параметры](#дополнительные-параметры-1)
    - [Пример использования](#пример-использования)
- [Общий запуск тестов](#общий-запуск-тестов)
- [Описание тестов](#описание-тестов)
  - [test_docker_manager.py](#test_docker_managerpy)
  - [test_perf.py](#test_perfpy)
    - [Практический пример: добавление тестового сценария](#практический-пример-добавление-тестового-сценария)
  - [test_upgrade.py](#test_upgradepy)
    - [Практический пример: добавление тестового сценария для модуля Upgrade](#практический-пример-добавление-тестового-сценария-для-модуля-upgrade)

## Performance модуль

**Важно:** данный модуль не является заменой утилите [pgbench](https://www.postgresql.org/docs/current/pgbench.html). 

### Почему не pgbench?

Performance модуль предназначен для автоматизации тестирования производительности в рамках заданных сценариев, описанных в YAML-манифестах. Он выполняет следующие задачи:
- Инициализацию базы данных.
- Запуск и измерение времени выполнения отдельных SQL-запросов (timing queries).
- Анализ планов выполнения запросов (explain queries) и сравнение их с ожидаемыми результатами.

В отличие от pgbench, который является полноценным инструментом нагрузочного тестирования и способен симулировать множество параллельных соединений для получения статистических данных о производительности базы данных под нагрузкой, Performance модуль фокусируется на проверке корректности конфигураций и сравнении фактического времени выполнения запросов с заранее заданными ожиданиями. Это позволяет интегрировать тестирование производительности в CI/CD процессы и быстро обнаруживать отклонения от эталонных показателей без необходимости проведения сложных нагрузочных тестов.

Таким образом, Performance модуль предназначен для сценарного тестирования и валидации изменений, а не для детального анализа производительности в условиях реальной многопользовательской нагрузки.

## Структура директорий

Директории проекта организованы следующим образом:
```sh
items/
└── your_scenario_name/
    ├── cases/
    │   ├── case_1/
    │   │   ├── pre_hook.sh
    │   │   ├── post_hook.sh
    │   │   ├── explain_query_1.sql
    │   │   ├── explain_query_2.sql
    │   │   ├── explain_expected_1.txt
    │   │   ├── explain_expected_2.txt
    │   │   ├── explain_expected_3.txt
    │   │   ├── timing_query_1.sql
    │   │   └── timing_query_2.sql
    │   ├── case_2/
    │   │   ├── pre_hook.sh
    │   │   ├── explain_query.sql
    │   │   └── explain_expected_1.txt
    │   └── ...
    ├── conf.yaml
    ├── fill_db.sh            # Скрипт инициализации базы данных (db_initial_script).
    └── initial_setup.sh      # Опциональный скрипт для предварительной настройки (initial_script).
```

- **items/**: Содержит различные сценарии тестирования. Каждый сценарий имеет свою собственную директорию.
  - **your_scenario_name/**: Замените на имя вашего сценария.
    - **cases/**: Содержит тестовые кейсы.
      - **case_N/**: Каждый тестовый кейс — это директория с необходимыми файлами.
    - **conf.yaml**: Конфигурационный манифест для сценария.
    - **fill_db.sh**: Скрипт для инициализации базы данных.
    - **initial_setup.sh**: Опциональный скрипт (sh или py).

- fill_db.sh: Скрипт инициализации базы данных. В данном скрипте можно, например, установить расширение и добавить его в параметр shared_preload_libraries или выполнить другую базовую настройку, необходимую для получения базового и корректно инициализированного инстанса БД.
- initial_setup.sh: Опциональный скрипт (sh или py), который выполняется сразу после запуска базы данных с минимальной настройкой, но перед применением полной конфигурации PostgreSQL. Этот скрипт можно использовать для предварительной настройки БД (например, для загрузки дополнительных данных или установки специфических настроек), если это необходимо для тестового сценария.


## Конфигурационный манифест (`conf.yaml`)

Файл `conf.yaml` является основным конфигурационным файлом для вашего сценария. Он определяет глобальные параметры, конфигурации баз данных и тестовые кейсы.

### Глобальные параметры

```yaml
kind: perf
db_params:
  - db_type: ttdb
    db_version: 15.6.1
    db_edition: se-1c
    db_port: 5440
  - db_type: pgdg
    db_version: 15.6.2
    db_port: 5443
db_initial_script: fill_db.sh
configuration: 1c.conf
initial_script: init_additional.sh
docker:
  host_port: 5430
  container_port: 5432
  container_name: pg_orchestrator_container
  registry: 'your_registry_url'
  image: 'your_docker_image'
```

kind: Тип сценария. Для тестирования производительности установите значение perf, для тестирования сценария обновления upgrade.
db_params: Список конфигураций баз данных для тестирования.

    db_type: Тип базы данных (ttdb или pgdg).
    db_version: Версия базы данных.
    db_edition: (Опционально) Редакция базы данных, например, se-1c.
    db_port: Порт для доступа к базе данных на хосте.

db_initial_script: Путь к скрипту инициализации базы данных (fill_db.sh).
configuration:  (Опционально) Конфигурационный файл для PostgreSQL (например, 1c.conf).
initial_script: (Опционально) Скрипт, который выполняется на чистом кластере.
docker: Список параметров для работы docker-контейнера.

    image: Docker-образ для использования в контейнере.
    registry: URL реестра Docker.

### Тестовые кейсы

Тестовые кейсы определяются под ключом cases в conf.yaml:
```yaml
cases:
  - name: case_1
    pre_hook: pre_hook.sh
    post_hook: post_hook.sh
    explain_queries:
      - query: explain_query_1.sql
        expected:
          - explain_expected_1.txt
          - explain_expected_2.txt
      - query: explain_query_2.sql
        expected:
          - explain_expected_3.txt
    timing_queries:
      - query: timing_query_1.sql
        expected_time_ms: 1500
      - query: timing_query_2.sql
        expected_time_ms: 2000
  - name: case_2
    pre_hook: pre_hook.sh
    explain_queries:
      - query: explain_query.sql
        expected:
          - explain_expected_1.txt
  - name: case_3
    timing_queries:
      - query: timing_query.sql
        expected_time_ms: 1000
  - name: case_4
    pre_hook: pre_hook.sh
    # Дополнительные настройки
```
### Поля

    name: Имя тестового кейса (должно соответствовать имени директории в cases/).
    pre_hook: (Опционально) Скрипт для выполнения перед тестовым кейсом. Может быть файлом .sh или .py.
    post_hook: (Опционально) Скрипт для выполнения после тестового кейса.
    explain_queries: (Опционально) Список запросов для анализа плана выполнения.
        query: Путь к файлу SQL с запросом.
        expected: Список файлов с ожидаемыми планами выполнения.
    timing_queries: (Опционально) Список запросов для измерения времени выполнения.
        query: Путь к файлу SQL с запросом.
        expected_time_ms: Ожидаемое время выполнения в миллисекундах.
### Дополнительные параметры

    performance_coefficient: Коэффициент быстродействия системы, значение от 0.1 до 1.0, где 1.0 — максимально быстрая система. 
    Используется для корректировки ожидаемого времени выполнения запросов.
    Если коэффициент меньше 1.0, ожидаемое время выполнения запросов увеличивается, что отражает менее производительную систему.

### Пример использования performance_coefficient

Если вы ожидаете, что система, на которой запускаются тесты, медленнее эталонной, вы можете установить коэффициент быстродействия, например, 0.8. Это увеличит допустимое время выполнения запросов на 25% (так как 1 / 0.8 = 1.25).

````yaml
performance_coefficient: 0.8
````

### Пример timing_queries с дробным ожидаемым временем

```yaml
timing_queries:
  - query: timing_query.sql
    expected_time_ms: 1234.56
```

## Upgrade модуль

pg_orchestrator предоставляет так же модуль для автоматизации обновления баз данных PostgreSQL. Он поддерживает различные сценарии обновления, такие как использование `pg_upgrade`, применение `minor` обновлений, и полное резервное копирование базы данных с помощью `pg_dumpall`. Модуль позволяет определять последовательность шагов обновления, параметры базы данных и конфигурации с использованием YAML-манифестов. Автоматизируется настройка Docker-контейнеров и выполнение обновлений с использованием заданных сценариев.

## Структура директорий

Директории проекта организованы следующим образом:
```sh
items/
└── upgrade_scenario/
    ├── conf.yaml
    ├── scripts/
    │   ├── step_1_pre_upgrade.sh
    │   ├── step_2_post_upgrade.sh
    │   └── ...
```

- **items/**: Содержит различные сценарии обновления. Каждый сценарий имеет свою собственную директорию.
  - **upgrade_scenario/**: Директория сценария обновления.
    - **conf.yaml**: Основной конфигурационный файл для сценария.
    - **scripts/**: Каталог со скриптами, используемыми на разных этапах обновления.

## Конфигурационный манифест (`conf.yaml`)

Файл `conf.yaml` является основным конфигурационным файлом для сценария обновления. Он определяет параметры базы данных, Docker-контейнера и последовательность шагов обновления.

### Глобальные параметры

```yaml
kind: upgrade
initial_pre_scripts:
  - setup_environment.sh
initial_post_scripts:
  - cleanup_environment.sh
db_args:
  initdb: --encoding=UTF8 --locale=ru_RU.UTF-8
db_version: 14.11.0
db_edition: be
package: tantor-be-server-15_15.10.0_amd64.deb
docker:
  host_port: 5430
  container_port: 5432
  container_name: pg_orchestrator_container
  registry: 'your_registry_url'
  image: 'your_docker_image'
steps:
  - db_version: 15.6.0
    db_edition: se
    type: pg_upgrade
    pre_scripts:
      - prepare_upgrade.sh
    post_scripts:
      - finalize_upgrade.sh
    args:
      pg_upgrade: --link
  - db_version: 15.6.1
    db_edition: se
    type: minor
  - db_version: 16.2.0
    db_edition: se
    type: pg_dumpall
```

### Поля

- **kind**: Тип сценария. Для работы с `upgrade` установите значение `upgrade`.
- **initial_pre_scripts**: (Опционально) Скрипты, выполняемые до начала сценария.
- **initial_post_scripts**: (Опционально) Скрипты, выполняемые после завершения сценария.
- **db_args**: Параметры для инициализации базы данных, такие как `initdb`.
- **db_version**: Начальная версия базы данных.
- **db_edition**: Начальная редакция базы данных (например, `be` или `se`). Работает только с `db_type: ttdb`.
- **package**: (Опционально) Имя пакета СУБД, откуда будет установлена база данных. Работает только с `db_type: ttdb`.
- **docker**: Параметры для настройки Docker-контейнера.
  - **host_port**: Порт хоста для контейнера.
  - **container_port**: Порт внутри контейнера.
  - **container_name**: Имя контейнера.
  - **registry**: URL реестра Docker.
  - **image**: Имя Docker-образа.
- **steps**: Список шагов обновления.
  - **db_version**: Версия базы данных после шага.
  - **db_edition**: Редакция базы данных после шага.
  - **type**: Тип обновления.
    - **pg_upgrade**: Использует команду `pg_upgrade` для обновления базы данных.
    - **minor**: Применяет `minor` обновление (`minor` release).
    - **pg_dumpall**: Полное резервное копирование базы данных с использованием `pg_dumpall`.
  - **pre_scripts**: (Опционально) Скрипты, выполняемые перед шагом обновления.
  - **post_scripts**: (Опционально) Скрипты, выполняемые после шага обновления.
  - **args**: Дополнительные параметры для конкретного шага, такие как опции для `pg_upgrade`.

### Дополнительные параметры

- **package**: Это поле используется для указания наименования пакета СУБД, откуда будет выполняться установка. Работает только при использовании `db_type: ttdb`. Полезно в случаях, когда требуется явно указать файл пакета базы данных для установки. Если поле не задано, установка будет происходить из настроенного источника, например, из Nexus или другого менеджера пакетов. Пример значения: `tantor-be-server-15_15.10.0_amd64.deb`.

### Пример использования

Этот сценарий последовательно выполнит шаги обновления, описанные в `conf.yaml`. Например, сначала выполнится обновление с использованием `pg_upgrade`, затем будет применено `minor` обновление, а в конце создастся полный дамп базы данных. Чтобы запустить сценарий, используйте аналогичные команды, как для модуля производительности, но укажите сценарий `upgrade` в качестве входного параметра.

## Тестирование PostgreSQL Orchestrator

### Описание выполняемых тестов

#### **`test_docker_manager.py`**
Покрывает функциональность класса `DockerContainerManager`, включая:
- **Инициализация менеджера**:
  - `test_init_success`: Проверяет успешную инициализацию DockerContainerManager с корректными параметрами.
  - `test_init_docker_exception`: Проверяет обработку ошибок, если Docker демон недоступен.
- **Управление контейнерами**:
  - Проверка и удаление существующего контейнера (`test_check_and_remove_existing_container_container_exists`, `test_check_and_remove_existing_container_container_not_found`).
  - Запуск контейнера (`test_start_container_success`, `test_start_container_container_error`).
  - Остановка контейнера (`test_stop_container_success`, `test_stop_container_no_container`).
- **Управление образами**:
  - Проверка наличия образа (`test_check_image_exists_or_pull_image_exists`).
  - Загрузка образа при его отсутствии (`test_check_image_exists_or_pull_image_not_found_no_registry`).
- **Выполнение команд внутри контейнера**:
  - Успешное выполнение команды (`test_exec_command_success`).
  - Обработка ошибок выполнения команды (`test_exec_command_failure`).

#### **`test_perf.py`**
Проверяет производительность и корректность работы модуля `Performance`:
- **`test_run_perf`**:
  - Выполнение сценария тестирования производительности на основе конфигурационного манифеста.
  - Очистка результатов тестов для удобства сравнения.
  - Сравнение фактических результатов с ожидаемыми с помощью библиотеки `DeepDiff`.
  - Сохранение результатов тестов в YAML-файл и сравнение с эталоном.

##### Практический пример: добавление тестового сценария
Для самостоятельного добавления тестового сценария выполните следующие шаги:

1. Создайте структуру директорий для теста:
   ```sh
   tests/perf_test/
   ├── 1c.conf
   ├── cases
   │   └── case_1
   │       ├── explain_expected_1.txt
   │       ├── explain_query.sql
   │       ├── timing_expected.txt
   │       └── timing_query.sql
   ├── conf.yaml
   ├── expected
   │   └── conf.yaml
   ├── fill_db.sh
   └── results
       └── conf.yaml
   ```

2. Подготовьте необходимые файлы:
   - **`fill_db.sh`**: Скрипт для начальной инициализации базы данных. Укажите команды для заполнения таблиц тестовыми данными.
   - **`1c.conf`**: Конфигурационный файл для настройки параметров PostgreSQL, таких как shared_buffers, work_mem и т.д.
   - **`cases/case_1/`**:
     - **`explain_query.sql`**: SQL-запрос для анализа плана выполнения.
     - **`explain_expected_1.txt`**: Ожидаемый результат выполнения EXPLAIN для запроса.
     - **`timing_query.sql`**: SQL-запрос для измерения времени выполнения.
     - **`timing_expected.txt`**: Ожидаемое время выполнения запроса.
   - **`conf.yaml`**: Главный конфигурационный файл сценария:
     ```yaml
     kind: perf
     db_params:
       - db_type: ttdb
         db_version: 15.6.1
         db_port: 5440
     db_initial_script: fill_db.sh
     configuration: 1c.conf
     docker:
       image: your_docker_image
       registry: your_registry_url
     cases:
       - name: case_1
         explain_queries:
           - query: cases/case_1/explain_query.sql
             expected:
               - cases/case_1/explain_expected_1.txt
         timing_queries:
           - query: cases/case_1/timing_query.sql
             expected_time_ms: 1000
     ```
   - **`expected/conf.yaml`**: Ожидаемые результаты тестов, сгенерированные вручную или с использованием предыдущего успешного тестового запуска.

3. Запустите тесты:
   ```sh
   pytest tests/test_perf.py
   ```

4. Проверьте результаты:
   - Сравните фактические результаты из `results/conf.yaml` с ожидаемыми в `expected/conf.yaml`.
   - Убедитесь, что отличий нет. Если есть, исправьте либо тестовые данные, либо ожидаемые значения.

#### **`test_upgrade.py`**
Тесты для модуля `Upgrade`:
- **Сценарий обновления**:
  - `test_upgrade_scenario`: Проверяет вызовы необходимых функций, таких как `run_migration`, и работу с контейнерами Docker.
- **Проверка наличия скриптов и пакетов**:
  - `test_check_scripts_exist`: Проверяет существование всех скриптов, указанных в конфигурации.
  - `test_check_packages_exist`: Проверяет наличие указанных пакетов в директории.
- **Подготовка окружения**:
  - `test_prepare_environment`: Убеждается в создании необходимых директорий и файлов для выполнения сценария обновления.
- **Выполнение шагов обновления**:
  - Minor обновления (`test_minor_step`).
  - Создание резервной копии с помощью `pg_dumpall` (`test_pg_dumpall_step`).
- **Логирование и обработка ошибок**:
  - Логирование ошибок `pg_upgrade` и создание логов в случае сбоя (`test_pg_upgrade_error_logs`).
  - Обработка ошибок SQL-скриптов (`test_run_sql_script_error_parsing`).

##### Практический пример: добавление тестового сценария для модуля `Upgrade`
Для добавления тестового сценария выполните следующие шаги:

1. Создайте структуру директорий для теста аналогично модулю `Performance`:
   ```sh
   tests/upgrade_test/
   ├── conf.yaml
   ├── scripts
       ├── pre_upgrade.sh
       └── post_upgrade.sh
   ```

2. Подготовьте файлы:
   - **`conf.yaml`**: Главный конфигурационный файл сценария:
     ```yaml
     kind: upgrade
     db_type: ttdb/pgdg
     db_version: 14.11.0
     db_edition: se
     docker:
       host_port: 5430
       container_port: 5445
       container_name: "test_container"
       registry: "your_registry"
       image: "your_docker_image"
     steps:
       - db_version: 15.6.0
         db_edition: se
         type: pg_upgrade
       - db_version: 15.10.0
         db_edition: se
         type: minor
         args:
           pg_upgrade: --link
       - db_version: 16.6.0
         db_edition: se
         type: pg_dumpall
     ```
   - **`scripts/`**: Скрипты для выполнения до и после обновления.
   - **`packages/`**: Пакет для обновления базы данных.
   - **`expected/conf.yaml`**: Ожидаемые результаты сценария.

3. Запустите тесты:
   ```sh
   pytest tests/test_upgrade.py
   ```
