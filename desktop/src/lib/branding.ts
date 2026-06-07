/** Public assets — use BASE_URL so paths work under Electron file:// */
const base = import.meta.env.BASE_URL;

export const TILTPROOF_LOGO_URL = `${base}tiltproof-logo.png`;
export const TILTPROOF_ICON_URL = `${base}tiltproof-icon.png`;

export const gameThumbnailUrl = (filename: string) => `${base}games/${filename}`;
