#!/bin/sh
# Chromium must keep tabs, omnibox, back/forward. jlesage kiosks the main
# window (undecorated + below); that makes Chromium go fullscreen and hide chrome.
set -eu

RC=/var/run/openbox/rc.xml
[ -f "$RC" ] || exit 0

# Replace the generated kiosk rule if 10-openbox still emitted one.
if grep -q 'Main window should be maximized' "$RC" 2>/dev/null; then
    awk '
        BEGIN { skip = 0 }
        /Main window should be maximized/ {
            skip = 1
            print "  <!-- Prims: Chromium keeps tabs/omnibox. Never kiosk-fullscreen. -->"
            print "  <application class=\"Chromium*\">"
            print "    <decor>no</decor>"
            print "    <maximized>true</maximized>"
            print "    <fullscreen>no</fullscreen>"
            print "    <layer>normal</layer>"
            print "  </application>"
            next
        }
        skip && /<\/application>/ { skip = 0; next }
        skip { next }
        { print }
    ' "$RC" > "$RC.prims" && mv "$RC.prims" "$RC"
elif ! grep -q 'Prims: Chromium keeps' "$RC" 2>/dev/null; then
    awk '
        /<\/applications>/ {
            print "  <!-- Prims: Chromium keeps tabs/omnibox. Never kiosk-fullscreen. -->"
            print "  <application class=\"Chromium*\">"
            print "    <decor>no</decor>"
            print "    <maximized>true</maximized>"
            print "    <fullscreen>no</fullscreen>"
            print "    <layer>normal</layer>"
            print "  </application>"
        }
        { print }
    ' "$RC" > "$RC.prims" && mv "$RC.prims" "$RC"
fi

chown "${USER_ID:-1000}:${GROUP_ID:-1000}" "$RC" 2>/dev/null || true
