<template>
  <svg
    ref="root"
    class="mascot"
    :class="`is-${state}`"
    viewBox="13 12 174 174"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    :aria-label="label"
  >
    <!-- 头部：几乎占满整个圆，只在四周留出均匀内边距 -->
    <rect class="m-body" x="18" y="16" width="164" height="168" rx="52" />
    <!-- 机身接缝：内缩一圈的细线，白底上也能看清头部边界 -->
    <rect class="m-body-seam" x="27" y="25" width="146" height="150" rx="43" />

    <!-- 面罩 -->
    <rect class="m-visor" x="38" y="36" width="124" height="100" rx="28" />
    <!-- 思考态的扫描线 -->
    <rect class="m-scan" x="50" y="44" width="100" height="6" rx="3" />

    <!-- 眼睛：外层跟随鼠标位移，内层统一眨眼 -->
    <g class="m-eyes" :style="{ transform: `translate(${look.x}px, ${look.y}px)` }">
      <g class="m-lids">
        <rect class="m-eye" x="71" y="62" width="14" height="30" rx="7" />
        <rect class="m-eye" x="115" y="62" width="14" height="30" rx="7" />
      </g>
    </g>

    <!-- 嘴：说话态做开合 -->
    <rect class="m-mouth" x="88" y="106" width="24" height="5" rx="2.5" />
  </svg>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = withDefaults(
  defineProps<{
    /** idle 待机眨眼 / thinking 思考扫描 / speaking 语音播报 */
    state?: 'idle' | 'thinking' | 'speaking'
    label?: string
    /** 是否让眼睛跟随鼠标；聊天列表里的大量小头像应关闭以免无谓监听 */
    track?: boolean
  }>(),
  { state: 'idle', label: 'AI 助手', track: true },
)

const root = ref<SVGSVGElement | null>(null)
// viewBox 单位下的眼珠偏移，最大水平 6、垂直 4，保证 58px 下也能看出转动
const look = ref({ x: 0, y: 0 })

let frame = 0
let pointer: { x: number; y: number } | null = null

function applyLook() {
  frame = 0
  const el = root.value
  if (!el || !pointer) return
  const rect = el.getBoundingClientRect()
  if (!rect.width) return
  const dx = pointer.x - (rect.left + rect.width / 2)
  const dy = pointer.y - (rect.top + rect.height / 2)
  const dist = Math.hypot(dx, dy) || 1
  // 光标离得越近，偏移越收敛，避免眼睛在中心附近来回抽搐
  const reach = Math.min(1, dist / 240)
  look.value = {
    x: Number(((dx / dist) * reach * 6).toFixed(2)),
    y: Number(((dy / dist) * reach * 4).toFixed(2)),
  }
}

function onPointerMove(e: PointerEvent) {
  pointer = { x: e.clientX, y: e.clientY }
  if (!frame) frame = requestAnimationFrame(applyLook)
}

onMounted(() => {
  if (props.track) window.addEventListener('pointermove', onPointerMove, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('pointermove', onPointerMove)
  if (frame) cancelAnimationFrame(frame)
})
</script>

<style scoped>
.mascot {
  --m-shell: #4f46e5;
  --m-visor: #1e1b4b;
  --m-soft: #a5b4fc;

  display: block;
  width: 100%;
  height: 100%;
}

.m-body { fill: var(--m-shell); }

.m-body-seam {
  fill: none;
  stroke: #ffffff;
  stroke-width: 4;
  opacity: 0.25;
}

.m-visor { fill: var(--m-visor); }
.m-scan { fill: var(--m-soft); opacity: 0; }

/* 跟随鼠标：加一点过渡让眼珠移动更顺滑 */
.m-eyes {
  transition: transform 0.12s linear;
}

.m-eye { fill: var(--m-soft); }

.m-lids {
  transform-box: fill-box;
  transform-origin: center;
}

.m-mouth {
  fill: var(--m-soft);
  transform-box: fill-box;
  transform-origin: center;
}

@media (prefers-reduced-motion: no-preference) {
  /* 待机：缓慢眨眼 */
  .mascot.is-idle .m-lids {
    animation: m-blink 4.6s infinite;
  }

  /* 思考：眼睛呼吸 + 面罩内扫描线巡回 */
  .mascot.is-thinking .m-lids {
    animation: m-eye-pulse 1.1s ease-in-out infinite;
  }
  .mascot.is-thinking .m-scan {
    animation: m-scan 1.5s ease-in-out infinite;
  }

  /* 播报：嘴部开合，和 TTS 的 speaking 状态联动 */
  .mascot.is-speaking .m-mouth {
    animation: m-talk 0.75s ease-in-out infinite;
  }
}

@keyframes m-blink {
  0%, 92%, 100% { transform: scaleY(1); }
  94%, 96% { transform: scaleY(0.08); }
  98% { transform: scaleY(1); }
}

@keyframes m-eye-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

@keyframes m-scan {
  0% { transform: translateY(0); opacity: 0; }
  15%, 85% { opacity: 0.55; }
  100% { transform: translateY(78px); opacity: 0; }
}

/* 说话节奏按音节起伏，而不是匀速抽搐 */
@keyframes m-talk {
  0%, 100% { transform: scaleY(1); }
  18% { transform: scaleY(1.9); }
  36% { transform: scaleY(1.1); }
  58% { transform: scaleY(2.2); }
  78% { transform: scaleY(1.05); }
}
</style>
