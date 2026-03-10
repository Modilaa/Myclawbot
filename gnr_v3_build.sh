#!/usr/bin/env bash
set -euo pipefail

W=/data/.openclaw/workspace
S=$W/content_factory_2026/outputs/share

# 1) Visual cutmap
ffmpeg -y \
  -i "$S/story1_clip1.mp4" \
  -i "$S/story1_clip2.mp4" \
  -i "$S/story1_clip3.mp4" \
  -i "$S/story2_clip.mp4" \
  -filter_complex "
[0:v]trim=0:2,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s1];
[1:v]trim=2:5,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s2];
[3:v]trim=0:4,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s3];
[1:v]trim=9:13,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s4];
[2:v]trim=0:4,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s5];
[1:v]trim=16:20,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s6];
[0:v]trim=2:9,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s7];
[2:v]trim=4:11,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s8];
[1:v]trim=20:30,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[s9];
[s1][s2][s3][s4][s5][s6][s7][s8][s9]concat=n=9:v=1:a=0[v]
" \
  -map "[v]" -r 30 -c:v libx264 -pix_fmt yuv420p "$W/gnr_v3_visual_only.mp4"

# 2) Audio layer (bgm + impacts)
ffmpeg -y \
  -i "$W/gnr_v3_visual_only.mp4" \
  -stream_loop -1 -i "$S/story2_bgm.m4a" \
  -f lavfi -t 0.18 -i "sine=frequency=1100:sample_rate=44100" \
  -f lavfi -t 0.22 -i "sine=frequency=70:sample_rate=44100" \
  -filter_complex "
[1:a]atrim=0:42.73,volume=0.20[bgm];
[2:a]volume=0.45,adelay=0|0[sfx1];
[2:a]volume=0.38,adelay=13000|13000[sfx2];
[3:a]volume=0.55,adelay=17000|17000[sfx3];
[2:a]volume=0.40,adelay=35000|35000[sfx4];
[bgm][sfx1][sfx2][sfx3][sfx4]amix=inputs=5:normalize=0[a]
" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest "$W/gnr_v3_final.mp4"

echo "Done: $W/gnr_v3_final.mp4"
