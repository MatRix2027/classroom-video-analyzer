import React, { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import videojs from 'video.js';
import type VideoJsPlayer from 'video.js/dist/types/player';
import 'video.js/dist/video-js.css';

interface VideoPlayerProps {
  src: string;
  /** 视频类型 MIME，默认 video/mp4 */
  mimeType?: string;
  /** 播放器高度，默认 400px */
  height?: number;
}

export interface VideoPlayerHandle {
  /** 跳转到指定秒数 */
  seekTo: (seconds: number) => void;
  /** 获取 video.js player 实例 */
  getPlayer: () => VideoJsPlayer | null;
}

/** video.js 播放器，暴露 seekTo 方法 */
const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, mimeType = 'video/mp4', height = 400 }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const playerRef = useRef<VideoJsPlayer | null>(null);

    // 初始化 player
    useEffect(() => {
      if (!videoRef.current) return;

      // 销毁旧实例
      if (playerRef.current) {
        playerRef.current.dispose();
        playerRef.current = null;
      }

      const player = videojs(videoRef.current, {
        controls: true,
        responsive: true,
        fluid: false,
        height: height,
        sources: [
          {
            src: src,
            type: mimeType,
          },
        ],
        preload: 'metadata',
      }) as unknown as VideoJsPlayer;

      playerRef.current = player;

      return () => {
        if (playerRef.current) {
          playerRef.current.dispose();
          playerRef.current = null;
        }
      };
    }, [src, mimeType, height]);

    // 暴露方法
    useImperativeHandle(ref, () => ({
      seekTo: (seconds: number) => {
        if (playerRef.current) {
          playerRef.current.currentTime(seconds);
          const paused = playerRef.current.paused();
          if (paused) {
            playerRef.current.play()?.catch(() => {});
          }
        }
      },
      getPlayer: () => playerRef.current,
    }));

    return (
      <div data-vjs-player style={{ width: '100%' }}>
        <video
          ref={videoRef}
          className="video-js vjs-big-play-centered vjs-fluid"
          playsInline
        />
      </div>
    );
  },
);

VideoPlayer.displayName = 'VideoPlayer';

export default VideoPlayer;
