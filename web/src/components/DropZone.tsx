import { useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { IconTestPipe } from '@tabler/icons-react';

interface DropZoneProps {
  onFile: (file: File) => void;
  fullBleed?: boolean;
}

/** The verify drop zone (§8.1 copy, verbatim). */
export function DropZone({ onFile, fullBleed = false }: DropZoneProps) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onFile(file);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Drop an image to run the litmus test on its provenance"
      onClick={() => inputRef.current?.click()}
      onKeyDown={onKeyDown}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border border-dashed px-6 text-center transition-colors duration-150 ease-out ${
        over ? 'border-ink bg-white' : 'border-line bg-white/60 hover:border-ink-2'
      } ${fullBleed ? 'min-h-[45vh] py-16' : 'py-12'}`}
    >
      <IconTestPipe size={28} stroke={1.5} className="text-ink-2" aria-hidden />
      <p className="max-w-md text-17 text-ink">
        Drop any image here to run the litmus test on its provenance.
      </p>
      <p className="text-13 text-ink-2">
        Works even on cropped or re-compressed copies. No account needed.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = '';
        }}
      />
    </div>
  );
}
