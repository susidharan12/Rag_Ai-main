/**
 * Photoreal "crumpled foil" orb, built entirely from an SVG lighting
 * filter - no images/video/WebGL:
 *   1. feTurbulence generates a fractal bump map (the wrinkle detail).
 *   2. feDisplacementMap warps a dark violet-to-black radial-gradient
 *      disc using that bump map, which crumples both its fill and its
 *      outer silhouette into the ridged, organic edge.
 *   3. feSpecularLighting relit against the SAME bump map produces the
 *      sharp bright ridge highlights; a SMIL <animate> sweeps the light
 *      azimuth so the highlights slowly travel across the surface.
 */
export default function BlobOrb({ size = 320, className = '' }) {
  return (
    <svg
      className={`blob-orb ${className}`}
      width={size}
      height={size}
      viewBox="0 0 400 400"
      role="img"
      aria-label="Animated orb"
    >
      <defs>
        <radialGradient id="orb-base" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#3b0764" />
          <stop offset="45%" stopColor="#1e0a3c" />
          <stop offset="100%" stopColor="#0a0612" />
        </radialGradient>

        <filter id="orb-crumple" x="-40%" y="-40%" width="180%" height="180%" colorInterpolationFilters="sRGB">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.011 0.015"
            numOctaves="5"
            seed="9"
            stitchTiles="stitch"
            result="noise"
          />

          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale="34"
            xChannelSelector="R"
            yChannelSelector="G"
            result="warped"
          />

          <feSpecularLighting
            in="noise"
            surfaceScale="9"
            specularConstant="1.7"
            specularExponent="16"
            lightingColor="#e9d5ff"
            result="spec"
          >
            <feDistantLight azimuth="235" elevation="55">
              <animate attributeName="azimuth" values="200;280;200" dur="16s" repeatCount="indefinite" />
            </feDistantLight>
          </feSpecularLighting>
          <feComposite in="spec" in2="warped" operator="in" result="specClip" />

          <feSpecularLighting
            in="noise"
            surfaceScale="9"
            specularConstant="0.9"
            specularExponent="20"
            lightingColor="#a855f7"
            result="spec2"
          >
            <feDistantLight azimuth="90" elevation="35">
              <animate attributeName="azimuth" values="60;140;60" dur="11s" repeatCount="indefinite" />
            </feDistantLight>
          </feSpecularLighting>
          <feComposite in="spec2" in2="warped" operator="in" result="specClip2" />

          <feMerge result="merged">
            <feMergeNode in="warped" />
            <feMergeNode in="specClip2" />
            <feMergeNode in="specClip" />
          </feMerge>
        </filter>
      </defs>

      <g style={{ transformOrigin: '200px 200px' }} className="blob-orb-spin">
        <circle cx="200" cy="200" r="150" fill="url(#orb-base)" filter="url(#orb-crumple)" />
      </g>
    </svg>
  )
}
