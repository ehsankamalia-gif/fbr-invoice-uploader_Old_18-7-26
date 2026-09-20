<script setup>
import { computed } from 'vue';

const props = defineProps({
  status: { type: String, required: true },
});

const classes = computed(() => {
  const s = (props.status || '').toUpperCase();
  if (s === 'ACTIVE' || s === 'PAID' || s === 'CLOSED') return 'bg-green-100 text-green-800';
  if (s === 'OVERDUE' || s === 'PARTIAL') return 'bg-yellow-100 text-yellow-800';
  if (s === 'PENDING') return 'bg-gray-100 text-gray-800';
  return 'bg-gray-100 text-gray-800';
});
</script>

<template>
  <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium" :class="classes">
    {{ status }}
  </span>
</template>
