#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [ -x "/usr/local/bin/python3" ]; then
    PYTHON_BIN="/usr/local/bin/python3"
elif [ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
elif [ -x "/Library/Frameworks/Python.framework/Versions/Current/bin/python3" ]; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3"
else
    PYTHON_BIN="$(which python3)"
fi

exec "$PYTHON_BIN" "$DIR/coretemp.py"
