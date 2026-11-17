<template>
  <div class="screenfull-trigger" @click="toggle">
    <QuitFullScreenIcon v-if="isFullscreen" :size="18" />
    <FullScreenIcon v-else :size="18" />
  </div>
</template>

<script setup>
import { useFullscreen } from '@vueuse/core'
import { FullScreenIcon } from '@solar-icons/vue/linear/full-screen'
import { QuitFullScreenIcon } from '@solar-icons/vue/linear/quit-full-screen'

const { isFullscreen, toggle } = useFullscreen()
</script>

<style lang="scss" scoped>
.screenfull-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
</style>
