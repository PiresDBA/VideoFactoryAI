--teste de tempo de cada cena do video

Get-ChildItem clip_*.mp4 | ForEach-Object { "$($_.Name) $(C:\Fabrica-de-videos\ffmpeg-9.0.2-essentials_build\bin\ffprobe -v error -show_entries format=duration -of csv=p=0 $_.FullName)" }