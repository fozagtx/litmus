import { VerifyFlow } from '../components/VerifyFlow';

export default function Verify() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
      <h1 className="sr-only">Verify a file</h1>
      <VerifyFlow fullBleed />
    </div>
  );
}
