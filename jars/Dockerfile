FROM jlesage/chromium:latest
COPY fastcompmgr.run /etc/services.d/fastcompmgr/run
COPY 12-prims-chrome.sh /etc/cont-init.d/12-prims-chrome.sh
COPY main-window-selection.xml /etc/openbox/main-window-selection.xml
RUN chmod 755 /etc/services.d/fastcompmgr/run /etc/cont-init.d/12-prims-chrome.sh && add-pkg xdotool ffmpeg
