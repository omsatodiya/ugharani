import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadGujarati } from "@remotion/google-fonts/NotoSansGujarati";

// The same look as the app (ugharani/static/theme.css).
export const C = {
  navy950: "#061233",
  navy900: "#0b1f4d",
  navy800: "#13306e",
  navy700: "#1d438f",
  blue500: "#2f6bff",
  blue600: "#1d4ed8",
  sky50: "#f4f8ff",
  sky100: "#e6effd",
  sky200: "#d3e3fa",
  muted: "#5a6a86",
  line: "rgba(11,31,77,0.1)",
  saffron: "#f08a24",
  good: "#15803d",
  goodBg: "#ecfdf3",
  bad: "#c0262d",
  badBg: "#fef2f2",
  warn: "#b45309",
  warnBg: "#fff7ed",
};

const serif = loadSerif("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily;
const inter = loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily;
const guj = loadGujarati("normal", { weights: ["400", "500", "600", "700"], subsets: ["gujarati"] }).fontFamily;

export const F = {
  serif: `${serif}, Georgia, serif`,
  sans: `${inter}, ${guj}, system-ui, sans-serif`,
  guj: `${guj}, ${inter}, sans-serif`,
};

export const FPS = 30;
export const s = (seconds: number) => Math.round(seconds * FPS);
