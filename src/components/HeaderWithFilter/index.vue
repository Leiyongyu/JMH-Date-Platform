<template>
  <span class="header-with-filter" @click.stop>
    <svg :class="['filter-icon', { active: isActive }]"
         viewBox="0 0 1024 1024" width="12" height="12"
         @click="onFilterClick">
      <path fill="currentColor" d="M911.2 128H112.8c-52.8 0-80 58.4-41.6 98.4L384 576v288c0 17.6 14.4 32 32 32h192c17.6 0 32-14.4 32-32V576l312.8-349.6c38.4-40 11.2-98.4-41.6-98.4z"/>
    </svg>
    <span class="label">{{ displayLabel }}</span>
  </span>
</template>

<script setup>
const props = defineProps({ field: String, title: String, filterInfo: Object, numeric: Boolean, label: String })
const emit = defineEmits(['openFilter'])
const isActive = computed(() => props.filterInfo && props.filterInfo[props.field])
const displayLabel = computed(() => props.label || props.field)

function onFilterClick(e) {
  emit('openFilter', props.field, e.currentTarget)
}
</script>

<style scoped>
.header-with-filter { display:inline-flex;align-items:center;gap:4px;cursor:default }
.filter-icon { color:#bfbfbf;cursor:pointer;flex-shrink:0 }
.filter-icon.active { color:#409EFF }
.filter-icon:hover { color:#409EFF }
.label { white-space:nowrap }
</style>
</style>
