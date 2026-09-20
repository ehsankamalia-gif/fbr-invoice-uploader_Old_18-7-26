<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  icon: { type: String, required: true },
  gradient: { type: String, default: 'from-blue-500 to-blue-600' },
  valueClass: { type: String, default: 'text-gray-800' },
});
</script>

<template>
  <div class="bg-white rounded-xl p-6 card-shadow card-hover">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-sm text-gray-500 mb-1">{{ label }}</p>
        <h3 class="text-3xl font-bold" :class="valueClass">{{ value }}</h3>
      </div>
      <div class="w-14 h-14 rounded-xl bg-gradient-to-br flex items-center justify-center" :class="gradient">
        <i :class="icon" class="text-white text-2xl"></i>
      </div>
    </div>
  </div>
</template>
