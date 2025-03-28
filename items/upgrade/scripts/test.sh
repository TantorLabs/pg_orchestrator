#!/bin/bash
set -exu -o pipefail
echo "-------> $0"


# Define the function, which is getting additional shared_preload_libraries
get_libs_by_edition() {
    local edition_name="$1"
    local file_path="/pg_orchestrator/items/upgrade/scripts/contrib.json"
    local base_libs="auth_delay,auto_explain,pg_stat_statements"

    # Extract additional libraries for the given edition from the JSON file
    local additional_libs=$(jq -r --arg edition "$edition_name" \
    '[.contrib[] | select(.editions[] == $edition and .shared_preload_libraries != "") | .shared_preload_libraries] | join(",")' $file_path)

    # Combine the base libraries with the additional ones and remove any duplicate commas
    if [[ "$additional_libs" != "" ]]; then
        echo "$base_libs,$additional_libs" | tr -s ','
    else
        echo "$base_libs"
    fi
}


_LOCAL_PG_DATA_DIR__="/tmp/new_data"

CONF_EDITION_SHORT_NAME__="se"
# Update the shared_preload_libraries for each edition
shared_libs=$(get_libs_by_edition "$CONF_EDITION_SHORT_NAME__")

if [ $CONF_EDITION_SHORT_NAME__ == "free" ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

if [ $CONF_EDITION_SHORT_NAME__ == "be" ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

if [ $CONF_EDITION_SHORT_NAME__ == "se" ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

if [ $CONF_EDITION_SHORT_NAME__ == "se-certified" ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

if [ "$CONF_EDITION_SHORT_NAME__" == "se-1c" ] && [ "$ARG_DISABLE_LLVM__" == 0 ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

if [ "$CONF_EDITION_SHORT_NAME__" == "se-1c" ] && [ "$ARG_DISABLE_LLVM__" == 1 ]; then
    cat >>$_LOCAL_PG_DATA_DIR__/postgresql.conf <<EOL
shared_preload_libraries='$shared_libs'
EOL
fi

su - postgres -c "pg_ctl -D /tmp/new_data/ restart"
_LOCAL_SU_EXT_PARAMS__=""
# How to show logs if DB is failed:
# su - postgres -c "/opt/tantor/db/15/bin/pg_ctl start -D /var/lib/postgresql/tantor-se-15/data -s -w -t 10"

# Get the list of available extensions
EXTENSIONS=$(su - postgres $_LOCAL_SU_EXT_PARAMS__ -c \
    "psql -t -c \"SELECT name FROM pg_available_extensions;\"")


# Loop over the extensions
for EXTENSION in $EXTENSIONS; do
    echo "Creating extension $EXTENSION"
    # Attempt to create each extension
    su - postgres $_LOCAL_SU_EXT_PARAMS__ \
        -c "psql -c \"CREATE EXTENSION IF NOT EXISTS \\\"$EXTENSION\\\" CASCADE;\""
done

#su - postgres $_LOCAL_SU_EXT_PARAMS__ \
#-c "psql -c \"DROP EXTENSION \\\"pg_columnar\\\" CASCADE;\""