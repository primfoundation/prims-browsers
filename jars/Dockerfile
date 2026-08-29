# Never :latest. Tag + index digest from Docker Hub 2026-08-28.
FROM jlesage/chromium:v26.08.3@sha256:a813afdc42dddceb6d429e2c1ab27a1b63596a951afebef12439af890d874696
COPY fastcompmgr.run /etc/services.d/fastcompmgr/run
COPY 12-prims-chrome.sh /etc/cont-init.d/12-prims-chrome.sh
COPY main-window-selection.xml /etc/openbox/main-window-selection.xml
RUN chmod 755 /etc/services.d/fastcompmgr/run /etc/cont-init.d/12-prims-chrome.sh && add-pkg xdotool ffmpeg
