/**
 * Crumpled-foil orb, built entirely from an SVG filter graph - no
 * images/video/WebGL. Two ideas combined:
 *
 *   1. "Veins": feTurbulence noise pushed through a steep feComponentTransfer
 *      gamma curve crushes everything but the brightest peaks to black,
 *      leaving a sparse network of bright cracks - far more predictable
 *      to tune than feSpecularLighting, which blows out or vanishes
 *      unpredictably depending on light angle/exponent. Two vein layers
 *      (violet, wider + white, sparser/brighter) give it depth.
 *   2. "Warp": a second, independent low-frequency turbulence feeds
 *      feDisplacementMap, which crumples both the vein pattern AND the
 *      circle's own outer edge into the organic, non-circular silhouette.
 *
 * Fills its container (width/height: 100%) - size it via CSS on the
 * wrapping element, not via props.
 */
export default function BlobOrb({ className = '' }) {
  return (
    <svg
      className={`blob-orb ${className}`}
      width="100%"
      height="100%"
      viewBox="0 0 400 400"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Animated orb"
    >
      <defs>
        <filter id="orb-crumple" x="-60%" y="-60%" width="220%" height="220%" colorInterpolationFilters="sRGB">
          {/* fine noise -> vein pattern */}
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.018 0.022"
            numOctaves="6"
            seed="11"
            stitchTiles="stitch"
            result="fineNoise"
          >
            <animate attributeName="seed" values="11;14;11" dur="22s" repeatCount="indefinite" />
          </feTurbulence>

          {/* separate, coarser noise -> silhouette/edge warp */}
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.007"
            numOctaves="4"
            seed="4"
            stitchTiles="stitch"
            result="warpNoise"
          />

          {/* medium violet veins - moderately sparse */}
          <feComponentTransfer in="fineNoise" result="veinsMid">
            <feFuncR type="gamma" amplitude="1" exponent="4.5" offset="0" />
            <feFuncG type="gamma" amplitude="1" exponent="4.5" offset="0" />
            <feFuncB type="gamma" amplitude="1" exponent="4.5" offset="0" />
          </feComponentTransfer>
          <feFlood floodColor="#c084fc" result="violetFlood" />
          <feComposite in="violetFlood" in2="veinsMid" operator="in" result="violetVeins" />

          {/* bright hot cracks - very sparse */}
          <feComponentTransfer in="fineNoise" result="veinsHot">
            <feFuncR type="gamma" amplitude="1" exponent="8" offset="0" />
            <feFuncG type="gamma" amplitude="1" exponent="8" offset="0" />
            <feFuncB type="gamma" amplitude="1" exponent="8" offset="0" />
          </feComponentTransfer>
          <feFlood floodColor="#f5eaff" result="whiteFlood" />
          <feComposite in="whiteFlood" in2="veinsHot" operator="in" result="whiteVeins" />

          <feFlood floodColor="#140726" result="darkFlood" />

          <feMerge result="colored">
            <feMergeNode in="darkFlood" />
            <feMergeNode in="violetVeins" />
            <feMergeNode in="whiteVeins" />
          </feMerge>

          <feDisplacementMap
            in="colored"
            in2="warpNoise"
            scale="70"
            xChannelSelector="R"
            yChannelSelector="G"
            result="warped"
          />

          <feComposite in="warped" in2="SourceAlpha" operator="in" />
        </filter>
      </defs>

      <g className="blob-orb-spin" style={{ transformOrigin: '200px 200px' }}>
        <circle cx="200" cy="200" r="150" fill="#140726" filter="url(#orb-crumple)" />
      </g>
    </svg>
  )
}
