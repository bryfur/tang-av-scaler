#!/bin/sh
# avandroid entry point: the caller's umask (androidrun passes it), then the command
[ -n "$ANDROIDRUN_UMASK" ] && umask "$ANDROIDRUN_UMASK"
exec "$@"
