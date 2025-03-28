# Here must be code, which creating tables, indexes, and filling this database some data

#!/bin/bash

# Создание таблицы my_table
psql -U postgres -c "
CREATE TABLE IF NOT EXISTS my_table (
    id SERIAL PRIMARY KEY,
    column1 TEXT,
    column2 TEXT
);
"

# Наполнение таблицы данными
psql -U postgres -c "
INSERT INTO my_table (column1, column2) VALUES
('value1', 'value2'),
('value3', 'value4'),
('value5', 'value6');
"

