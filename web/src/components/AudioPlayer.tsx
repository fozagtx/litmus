import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react';
import { fmtClock } from '../lib/format';
import { Button } from './ui';

const BUCKETS = 480;

/** Waveform player: real peaks from the decoded AudioBuffer, drawn on canvas. */
export function AudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [peaks, setPeaks] = useState<Float32Array | null>(null);
  const [decodeFailed, setDecodeFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setPeaks(null);
    setDecodeFailed(false);
    (async () => {
      try {
        const res = await fetch(src);
        if (!res.ok) throw new Error(String(res.status));
        const buf = await res.arrayBuffer();
        const ctx = new AudioContext();
        try {
          const audio = await ctx.decodeAudioData(buf);
          const data = audio.getChannelData(0);
          const out = new Float32Array(BUCKETS);
          const per = Math.max(1, Math.floor(data.length / BUCKETS));
          for (let i = 0; i < BUCKETS; i++) {
            let max = 0;
            const start = i * per;
            const end = Math.min(data.length, start + per);
            for (let j = start; j < end; j++) {
              const v = Math.abs(data[j]);
              if (v > max) max = v;
            }
            out[i] = max;
          }
          if (!cancelled) setPeaks(out);
        } finally {
          void ctx.close();
        }
      } catch {
        if (!cancelled) setDecodeFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [src]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);
    const played = duration > 0 ? time / duration : 0;
    const barWidth = rect.width / peaks.length;
    const mid = rect.height / 2;
    for (let i = 0; i < peaks.length; i++) {
      const h = Math.max(1, peaks[i] * (rect.height - 4));
      ctx.fillStyle = i / peaks.length <= played ? '#1a1917' : '#e3e0d8';
      ctx.fillRect(i * barWidth, mid - h / 2, Math.max(1, barWidth - 1), h);
    }
  }, [peaks, time, duration]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play();
    else audio.pause();
  };

  const seek = (event: MouseEvent<HTMLCanvasElement>) => {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas || duration <= 0) return;
    const rect = canvas.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    audio.currentTime = fraction * duration;
  };

  if (decodeFailed) {
    return <audio controls src={src} className="w-full" />;
  }

  return (
    <div className="rounded-card border border-line bg-white p-4">
      <div className="flex items-center gap-3">
        <Button
          type="button"
          onClick={toggle}
          aria-label={playing ? 'Pause narration' : 'Play narration'}
          className="px-3"
        >
          {playing ? (
            <IconPlayerPause size={16} stroke={1.75} aria-hidden />
          ) : (
            <IconPlayerPlay size={16} stroke={1.75} aria-hidden />
          )}
        </Button>
        <canvas
          ref={canvasRef}
          onClick={seek}
          className="h-16 min-w-0 flex-1 cursor-pointer"
          aria-label="Narration waveform, click to seek"
        />
        <span className="font-mono text-13 tabular-nums text-ink-2">
          {fmtClock(time)} / {fmtClock(duration)}
        </span>
      </div>
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        className="hidden"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
      />
    </div>
  );
}
