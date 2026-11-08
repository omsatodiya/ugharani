import React from "react";
import { Composition } from "remotion";
import { FPS } from "./theme";
import { Kinetic, TOTAL_KINETIC } from "./Kinetic";
import { Launch, TOTAL } from "./Video";

export const RemotionRoot: React.FC = () => (
  <>
    {/* The launch video: kinetic type cut to music. */}
    <Composition id="Launch" component={Kinetic} durationInFrames={TOTAL_KINETIC} fps={FPS} width={1920} height={1080} />
    <Composition id="LaunchSquare" component={Kinetic} durationInFrames={TOTAL_KINETIC} fps={FPS} width={1080} height={1080} />
    {/* The first cut: light screens, a longer call, no music. */}
    <Composition id="Classic" component={Launch} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
    <Composition id="ClassicSquare" component={Launch} durationInFrames={TOTAL} fps={FPS} width={1080} height={1080} />
  </>
);
