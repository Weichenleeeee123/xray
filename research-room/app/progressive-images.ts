export const officeImages = [
  { id: 'background', preview: '/research-assets/office-panorama-closed.q90.webp?v=d216fe3093d4', full: '/research-assets/office-panorama-closed.lossless.webp?v=ba600f10fb66' },
  { id: 'action', preview: '/research-assets/xiaoqi-action-cycles.q90.webp?v=e9c7687ccda8', full: '/research-assets/xiaoqi-action-cycles.lossless.webp?v=6b427be555eb' },
  { id: 'motion', preview: '/research-assets/office-motion-elements.q90.webp?v=9fa1b2430c9b', full: '/research-assets/office-motion-elements.lossless.webp?v=c0b30ae37133' },
  { id: 'door', preview: '/research-assets/office-panorama-door-open.q90.webp?v=9ebb2bcd1d1e', full: '/research-assets/office-panorama-door-open.lossless.webp?v=7556dc8849a0' },
  { id: 'walk', preview: '/research-assets/xiaoqi-walk-cycles.q90.webp?v=5175ea0c27c3', full: '/research-assets/xiaoqi-walk-cycles.lossless.webp?v=498ade702bfa' },
  { id: 'goose', preview: '/research-assets/goose-actions-v2.q90.webp?v=3d67729380fc', full: '/research-assets/goose-actions-v2.lossless.webp?v=0243a93bb58c' },
  { id: 'dossier', preview: '/research-assets/investigation-dossier.q90.webp?v=01e2a1297765', full: '/research-assets/investigation-dossier.lossless.webp?v=f9e0821eab92' },
] as const;

export type OfficeImageId = (typeof officeImages)[number]['id'];
export const previewSources = Object.fromEntries(
  officeImages.map(({ id, preview }) => [id, preview]),
) as Record<OfficeImageId, string>;

// Keep the preview in place until decoding succeeds, with one upgrade in flight.
export async function upgradeImages<T extends { id: string; full: string }>(
  assets: readonly T[],
  decode: (url: string, signal: AbortSignal) => Promise<void>,
  apply: (asset: T) => void,
  signal: AbortSignal,
) {
  for (const asset of assets) {
    if (signal.aborted) return;
    try {
      await decode(asset.full, signal);
    } catch {
      continue;
    }
    if (signal.aborted) return;
    apply(asset);
  }
}
