<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'

interface Props {
  talking?: boolean
  width?: number
  height?: number
  active?: boolean
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  talking: false,
  width: 160,
  height: 200,
  active: false,
  fallback: '',
})

const containerRef = ref<HTMLDivElement | null>(null)
const loaded = ref(false)
const failed = ref(false)

// 移动端 / 触屏设备不加载 WebGL 模型：pixi + Live2D 在手机上功耗高、掉帧明显，
// 直接使用静态头像保证面板交互流畅
const useStatic = typeof window !== 'undefined'
  && (window.matchMedia('(pointer: coarse)').matches || window.innerWidth <= 768)

let app: any = null
let model: any = null
let mouthValue = 0  // 当前嘴型张开度（0~1）
let mouthTimer: ReturnType<typeof setInterval> | null = null
let originalUpdate: ((...args: any[]) => void) | null = null

// 官方免费模型 Hiyori（服务器本地托管，public/live2d/Hiyori）
const MODEL_URL = '/live2d/Hiyori/Hiyori.model3.json'
const CUBISM_CORE_URL = '/live2d/live2dcubismcore.min.js'

let cubismCoreLoaded = false

function loadCubismCore(): Promise<void> {
  if (cubismCoreLoaded) return Promise.resolve()
  if ((window as any).Live2DCubismCore) { cubismCoreLoaded = true; return Promise.resolve() }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = CUBISM_CORE_URL
    script.async = true
    script.onload = () => { cubismCoreLoaded = true; resolve() }
    script.onerror = reject
    document.head.appendChild(script)
  })
}

function applyMouthValue() {
  if (!model?.internalModel?.coreModel) return
  try {
    const cm = model.internalModel.coreModel
    // 用 setParameterValueById 直接设置嘴型张开度
    cm.setParameterValueById('ParamMouthOpenY', mouthValue)
  } catch { /* ignore */ }
}

function startMouthAnimation() {
  if (!model) return
  stopMouthAnimation()
  // monkey-patch internalModel.update，在每帧更新前注入嘴型参数
  if (model.internalModel && !originalUpdate) {
    originalUpdate = model.internalModel.update.bind(model.internalModel)
    model.internalModel.update = (...args: any[]) => {
      applyMouthValue()
      originalUpdate!(...args)
    }
  }
  mouthTimer = setInterval(() => {
    mouthValue = 0.15 + Math.random() * 0.75
  }, 120)
}

function stopMouthAnimation() {
  if (mouthTimer) {
    clearInterval(mouthTimer)
    mouthTimer = null
  }
  mouthValue = 0
  // 恢复原始 update 方法
  if (model?.internalModel && originalUpdate) {
    model.internalModel.update = originalUpdate
    originalUpdate = null
  }
}

async function init() {
  if (useStatic || !containerRef.value || loaded.value || failed.value) return
  try {
    // 1. 先加载 Cubism Core SDK
    await loadCubismCore()

    // 2. 动态导入 pixi 和 live2d
    const PIXI = await import('pixi.js')
    ;(window as any).PIXI = PIXI

    const live2dMod = await import('pixi-live2d-display/lib/cubism4')
    const Live2DModel = live2dMod.Live2DModel || live2dMod.default?.Live2DModel
    if (!Live2DModel) throw new Error('Live2DModel not found in module')

    Live2DModel.registerTicker(PIXI.Ticker as any)

    // 强制使用 WebGL1，pixi-live2d-display 0.3.1 不完全兼容 WebGL2
    ;(PIXI.settings as any).PREFER_ENV = (PIXI as any).ENV?.WEBGL ?? 1

    app = new PIXI.Application({
      width: props.width,
      height: props.height,
      transparent: true,
      antialias: true,
      // 不使用 autoDensity 和高 resolution，避免 projectionMatrix 与 viewport 不匹配
      autoDensity: false,
      resolution: 1,
      preserveDrawingBuffer: true,
    })
    containerRef.value.appendChild(app.view as HTMLCanvasElement)

    // autoInteract 设为 false：pixi.js v7 的交互系统与 pixi-live2d-display 0.4.0 不兼容
    model = await Live2DModel.from(MODEL_URL, { autoInteract: false })

    // 模型定位：
    // - centeringTransform 会把原点从左上角移到中心：scale(1024) + translate(512, 512)
    // - 因此需要补偿 512 * scale 的偏移，让模型中心对齐 canvas 中心
    // - 角色实际只占模型纹理的一部分，需要放大约 2.85 倍才能填满 canvas
    const baseScale = Math.min(props.width / model.width, props.height / model.height)
    const scale = baseScale * 2.85
    model.scale.set(scale)
    const offset = 512 * scale
    model.x = props.width / 2 - offset
    model.y = props.height / 2 - offset
    app.stage.addChild(model)

    // pixi v5 中 renderer.gl 不是真正的 WebGL context，需要用 renderer.context.gl
    // patch 一下，让 pixi-live2d-display 能拿到正确的 gl
    if (!app.renderer.gl || !(app.renderer.gl instanceof WebGLRenderingContext)) {
      ;(app.renderer as any).gl = app.renderer.context.gl
    }

    // 强制设置 gl context
    if (app.renderer.gl) {
      model.glContextID = app.renderer.CONTEXT_UID
      model.internalModel.renderer.startUp(app.renderer.gl)
    }

    loaded.value = true
  } catch (e) {
    console.warn('[Live2D] 加载失败:', e)
    failed.value = true
    cleanup()
  }
}

function cleanup() {
  stopMouthAnimation()
  if (model) {
    try { model.destroy() } catch { /* ignore */ }
    model = null
  }
  if (app) {
    try { app.destroy(true, { children: true }) } catch { /* ignore */ }
    app = null
  }
}

watch(() => props.talking, (v) => {
  if (v) startMouthAnimation()
  else stopMouthAnimation()
})

// active 变为 true 时才初始化
watch(() => props.active, (v) => {
  if (v && !loaded.value && !failed.value) {
    init().catch(() => { failed.value = true; cleanup() })
  }
})

onMounted(() => {
  if (props.active) init().catch(() => { failed.value = true; cleanup() })
})

onBeforeUnmount(cleanup)
</script>

<template>
  <div class="live2d-wrap" :style="{ width: width + 'px', height: height + 'px' }">
    <div v-if="!failed && !useStatic" ref="containerRef" class="live2d-canvas"></div>
    <img v-if="(failed || useStatic) && fallback" :src="fallback" class="live2d-fallback" alt="AI 导员" />
    <div v-if="!loaded && !failed && !useStatic" class="live2d-loading">…</div>
  </div>
</template>

<style scoped>
.live2d-wrap {
  position: relative;
  display: inline-block;
  overflow: hidden;
}
.live2d-canvas {
  width: 100%;
  height: 100%;
}
.live2d-canvas canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
.live2d-fallback {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
}
.live2d-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #999;
}
</style>
