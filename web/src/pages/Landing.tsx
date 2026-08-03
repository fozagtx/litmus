import { IconCertificate, IconCrop, IconLock } from '@tabler/icons-react';
import { LinkButton, secondaryClass } from '../components/ui';
import { VerifyFlow } from '../components/VerifyFlow';

const THREE_UP = [
  {
    icon: IconCertificate,
    title: 'Born verifiable',
    body: 'Every generation is signed at birth: prompt, model, time, and author, sealed the moment it exists.',
  },
  {
    icon: IconLock,
    title: 'Sealed in WORM storage',
    body: 'Records live in compliance-locked storage. Write once, read forever, alter never.',
  },
  {
    icon: IconCrop,
    title: 'Survives the screenshot',
    body: "Perceptual fingerprints recover an asset's history from cropped, compressed, or messaged copies.",
  },
];

export default function Landing() {
  return (
    <div>
      <section className="mx-auto w-full max-w-6xl px-4 pb-14 pt-16 sm:px-6 sm:pt-24">
        <h1 className="max-w-3xl font-display text-44 text-ink">
          Your creative memory, sealed.
        </h1>
        <p className="mt-5 max-w-2xl text-17 text-ink-2">
          Litmus is a generation studio where every AI asset is born with a signed birth
          certificate, stored in write-once vault storage that nobody can rewrite. Not
          us. Not anyone.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <LinkButton to="/studio" variant="primary">
            Open the studio
          </LinkButton>
          <a href="#verify" className={secondaryClass}>
            Verify a file
          </a>
        </div>
      </section>

      <section id="verify" className="mx-auto w-full max-w-6xl scroll-mt-8 px-4 sm:px-6">
        <VerifyFlow />
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="font-display text-22 text-ink">How it works</h2>
        <div className="mt-8 grid gap-10 sm:grid-cols-3">
          {THREE_UP.map((item) => (
            <div key={item.title}>
              <item.icon size={26} stroke={1.5} className="text-ink" aria-hidden />
              <h3 className="mt-3 text-17 font-medium text-ink">{item.title}</h3>
              <p className="mt-1.5 text-15 text-ink-2">{item.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
