param(
    [string]$StreamName = "laptop",
    [string]$CameraName = "Integrated Webcam",
    [string]$RtspHost = "localhost",
    [int]$RtspPort = 8554
)

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    throw "ffmpeg was not found. Install FFmpeg and make it available on PATH."
}

# Fail early with a readable message rather than ffmpeg's device-enumeration
# error: DirectShow names differ per machine ("Integrated Webcam" here,
# "Integrated Camera" on other laptops). List them with:
#   ffmpeg -list_devices true -f dshow -i dummy
$devices = & $ffmpeg.Source -hide_banner -list_devices true -f dshow -i dummy 2>&1 | Out-String
if ($devices -notmatch [regex]::Escape("`"$CameraName`"")) {
    throw "DirectShow video device `"$CameraName`" was not found. Available devices:`n$devices"
}

$target = "rtsp://$RtspHost`:$RtspPort/$StreamName"
# -rtsp_transport tcp: MediaMTX runs in a container and only 8554 is
# published, so UDP RTP would be sent to unmapped ports and the session would
# time out after a few seconds. TCP interleaves the media over 8554 itself.
& $ffmpeg.Source -f dshow -video_size 1280x720 -framerate 30 -i "video=$CameraName" -an -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -f rtsp -rtsp_transport tcp $target
exit $LASTEXITCODE
