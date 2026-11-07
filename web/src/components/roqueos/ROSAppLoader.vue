<template>
  <div class="ros-app-loader" :class="`ros-app-loader--${state}`" :style="accentStyle">
    <div class="ros-app-loader__hero" :class="heroVariantClass">
      <img v-if="image" :src="image" :alt="title || ''" class="ros-app-loader__hero-img" />
      <q-icon v-else :name="resolvedIcon" :size="heroIconSize" />
    </div>

    <h3 class="ros-app-loader__title">{{ title }}</h3>

    <!-- File pill (e.g. the document being opened) takes precedence over a -->
    <!-- plain subtitle when provided. -->
    <p v-if="fileLabel" class="ros-app-loader__file">{{ fileLabel }}</p>
    <p v-else-if="displaySubtitle" class="ros-app-loader__text">{{ displaySubtitle }}</p>

    <div v-if="state === 'loading' && showBar" class="ros-app-loader__bar" aria-hidden="true">
      <span></span>
    </div>

    <ROSButton
      v-if="state !== 'loading' && showRetry && alguemOuveORetry()"
      variant="primary"
      icon="refresh"
      :label="retryLabel || t('common.retry')"
      class="ros-app-loader__retry"
      @click="$emit('retry')"
    />

    <!-- Extra content (secondary actions, hints) below the standard blocks. -->
    <slot />
  </div>
</template>

<script setup>
import { computed, getCurrentInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveAccent } from 'src/composables/useAppAccent'
import ROSButton from './ROSButton.vue'

const props = defineProps({
  // 'loading' | 'error' | 'empty' | 'no-server'
  state: { type: String, default: 'loading' },
  // Material icon name for the hero. Ignored when `image` is set.
  icon: { type: String, default: 'widgets' },
  // Optional branded image (svg/png) shown in the hero instead of an icon.
  image: { type: String, default: '' },
  // Accent hex (e.g. '#fa6800'); the rgb triplet is derived + sanitized.
  accent: { type: String, default: '#007aff' },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  // A filename-style pill (replaces subtitle when present).
  fileLabel: { type: String, default: '' },
  // Error/empty/no-server body text (overrides subtitle in those states).
  errorMessage: { type: String, default: '' },
  retryLabel: { type: String, default: '' },
  showRetry: { type: Boolean, default: true },
  showBar: { type: Boolean, default: true },
  heroIconSize: { type: String, default: '40px' },
})

defineEmits(['retry'])

// Botão que emite para ninguém é botão morto. Até 27/09/2026 o "Tentar novamente"
// aparecia em todo estado que não fosse `loading`, ouvisse alguém ou não: a lista
// vazia de Notas, a Captura de Tela no celular, a permissão do Gravador e o App Maker
// sem servidor mostravam um botão que não fazia nada. Agora ele só existe quando a
// tela que usa o loader escuta o `retry`. `onRetry` chega nos props do vnode mesmo
// com o evento declarado em `defineEmits`.
const instancia = getCurrentInstance()
const alguemOuveORetry = () => typeof instancia?.vnode.props?.onRetry === 'function'

const { t } = useI18n()

const resolvedIcon = computed(() => props.icon || 'widgets')

const accentStyle = computed(() => {
  const a = resolveAccent(props.accent)
  return { '--ros-loader-accent': a.hex, '--ros-loader-accent-rgb': a.rgb }
})

// Error / no-server states swap the hero gradient (red / muted) for clear intent.
const heroVariantClass = computed(() => {
  if (props.state === 'error') return 'ros-app-loader__hero--error'
  if (props.state === 'no-server' || props.state === 'empty') {
    return 'ros-app-loader__hero--muted'
  }
  return ''
})

const displaySubtitle = computed(() => {
  if (props.state === 'error' || props.state === 'no-server' || props.state === 'empty') {
    return props.errorMessage || props.subtitle
  }
  return props.subtitle
})
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

.ros-app-loader {
  // Cores de identidade deste app. Ficam aqui, e não em `tokens-root.scss`,
  // porque são do app e não do sistema — mas ficam como custom property
  // para que um tema consiga alcançá-las.
  --ros-app-loader-bg-1: #1b1d27;
  --ros-app-loader-bg-2: #14151c;
  --ros-app-loader-bg-3: #0d0e13;
  --ros-app-loader-bg-4: #5a5f6b;
  --ros-app-loader-bg-5: #3a3e47;
  --ros-app-loader-bg-6: rgba(120, 130, 145, 0.35);
  --ros-app-loader-bg-7: #ff5a4d;
  --ros-app-loader-bg-8: #c2362c;
  --ros-app-loader-shadow-1: rgba(255, 59, 48, 0.4);
}

// Canonical premium app preloader — the single source of the loading/state
// look first built for RoqueOffice + the Google apps: a warm-neutral dark
// backdrop with a drifting accent aurora, a floating hero icon with a pulsing
// halo, title + subtitle/file-pill, and an optional shimmer bar, all entering
// in a gentle cascade. The accent is injected per-use via CSS vars (sanitized
// in useAppAccent), so any app's colour works. Motion is killed in low-end mode.
.ros-app-loader {
  --ros-loader-accent: #{$ros-accent};
  --ros-loader-accent-rgb: 0, 122, 255;

  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 32px;
  width: 100%;
  height: 100%;
  min-height: 0;
  text-align: center;
  color: $ros-text;
  overflow: hidden;
  background: radial-gradient(
    ellipse at 50% 0%,
    var(--ros-app-loader-bg-1) 0%,
    var(--ros-app-loader-bg-2) 58%,
    var(--ros-app-loader-bg-3) 100%
  );

  // Drifting aurora mesh tinted with the app accent.
  &::before,
  &::after {
    content: '';
    position: absolute;
    border-radius: 50%;
    pointer-events: none;
    filter: blur(70px);
    z-index: 0;
  }
  &::before {
    width: 70%;
    height: 50%;
    top: -12%;
    left: -8%;
    background: radial-gradient(circle, rgba(var(--ros-loader-accent-rgb), 0.3), transparent 70%);
    animation: ros-loader-aurora-a 17s ease-in-out infinite;
  }
  &::after {
    width: 65%;
    height: 50%;
    bottom: -14%;
    right: -10%;
    background: radial-gradient(circle, rgba(var(--ros-loader-accent-rgb), 0.18), transparent 70%);
    animation: ros-loader-aurora-b 21s ease-in-out infinite;
  }

  // Premium entrance — blocks fade up in a gentle cascade.
  > * {
    position: relative;
    z-index: 1;
    animation: ros-loader-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
  }
  > *:nth-child(2) {
    animation-delay: 0.08s;
  }
  > *:nth-child(3) {
    animation-delay: 0.16s;
  }
  > *:nth-child(4) {
    animation-delay: 0.24s;
  }

  &__hero {
    position: relative;
    width: 84px;
    height: 84px;
    border-radius: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--ros-text-100);
    background: linear-gradient(
      135deg,
      var(--ros-loader-accent),
      rgba(var(--ros-loader-accent-rgb), 0.62)
    );
    box-shadow: 0 16px 40px rgba(var(--ros-loader-accent-rgb), 0.45);
    animation: ros-loader-float 5s ease-in-out infinite;

    &::after {
      content: '';
      position: absolute;
      inset: -14px;
      border-radius: 30px;
      background: radial-gradient(
        circle,
        rgba(var(--ros-loader-accent-rgb), 0.45),
        transparent 70%
      );
      z-index: -1;
      animation: ros-loader-halo 3s ease-in-out infinite;
    }

    &--muted {
      background: linear-gradient(135deg, var(--ros-app-loader-bg-4), var(--ros-app-loader-bg-5));
      box-shadow: 0 16px 40px var(--ros-shadow-40);
      &::after {
        background: radial-gradient(circle, var(--ros-app-loader-bg-6), transparent 70%);
      }
    }
    &--error {
      background: linear-gradient(135deg, var(--ros-app-loader-bg-7), var(--ros-app-loader-bg-8));
      box-shadow: 0 16px 40px var(--ros-app-loader-shadow-1);
      &::after {
        background: radial-gradient(circle, var(--ros-app-loader-shadow-1), transparent 70%);
      }
    }
  }

  &__hero-img {
    width: 46px;
    height: 46px;
    object-fit: contain;
  }

  &__title {
    margin: 4px 0 0;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
    color: $ros-text;
    /* `line-height` EXPLÍCITO é obrigatório: um `<h3>` cru herda o line-height
       global de heading (~50px neste font-size) e um título que quebra em duas
       linhas fica com um buraco entre elas. Mesmo defeito que a rule 24 já
       documenta no header do ROSModal; aqui ele aparecia em qualquer app cujo
       título de estado não coubesse numa linha (pego no QA do RoqueShield,
       2026-08-10). */
    line-height: 1.3;
  }

  &__text {
    margin: 0;
    max-width: 380px;
    font-size: var(--ros-text-base);
    line-height: 1.5;
    color: $ros-text-muted;
  }

  &__file {
    margin: 0;
    max-width: 80%;
    padding: 5px 12px;
    border-radius: var(--ros-radius-pill);
    font-size: var(--ros-text-sm);
    color: rgba(var(--ros-text-rgb), 0.82);
    background: rgba(var(--ros-loader-accent-rgb), 0.14);
    border: 1px solid rgba(var(--ros-loader-accent-rgb), 0.28);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__bar {
    position: relative;
    width: 180px;
    height: 4px;
    border-radius: var(--ros-radius-pill);
    overflow: hidden;
    background: $ros-fill-08;

    span {
      position: absolute;
      top: 0;
      left: 0;
      width: 40%;
      height: 100%;
      border-radius: var(--ros-radius-pill);
      background: linear-gradient(
        90deg,
        transparent,
        var(--ros-loader-accent),
        rgba(var(--ros-loader-accent-rgb), 0.5)
      );
      animation: ros-loader-bar 1.3s ease-in-out infinite;
    }
  }

  &__retry {
    margin-top: 4px;
  }
}

@keyframes ros-loader-aurora-a {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
    opacity: 0.7;
  }
  50% {
    transform: translate3d(6%, 5%, 0) scale(1.18);
    opacity: 1;
  }
}
@keyframes ros-loader-aurora-b {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1.05);
    opacity: 0.55;
  }
  50% {
    transform: translate3d(-7%, -6%, 0) scale(1.22);
    opacity: 0.85;
  }
}
@keyframes ros-loader-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-7px);
  }
}
@keyframes ros-loader-halo {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 0.85;
    transform: scale(1.12);
  }
}
@keyframes ros-loader-rise {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes ros-loader-bar {
  0% {
    left: -40%;
  }
  100% {
    left: 100%;
  }
}

html[data-low-end='1'] {
  .ros-app-loader::before,
  .ros-app-loader::after,
  .ros-app-loader__hero,
  .ros-app-loader__hero::after,
  .ros-app-loader > *,
  .ros-app-loader__bar span {
    animation: none;
  }
}
</style>
