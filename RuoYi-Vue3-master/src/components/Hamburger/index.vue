<template>
  <div class="hamburger-trigger" @click="toggleClick">
    <HamburgerMenuIcon :size="18" class="hamburger" :class="{ 'is-active': isActive }" />
  </div>
</template>

<script setup>
import { HamburgerMenuIcon } from '@solar-icons/vue/linear/hamburger-menu'

defineProps({
  isActive: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits()
const toggleClick = () => {
  emit('toggleClick')
}
</script>

<style scoped>
.hamburger-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.hamburger {
  transition: transform 0.25s ease;
}

.hamburger.is-active {
  transform: rotate(180deg);
}
</style>
