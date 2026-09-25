<script setup>
const INPUT_CLASS =
  'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition';

defineProps({
  label: { type: String, required: true },
  modelValue: { type: [String, Number, Boolean], default: '' },
  type: { type: String, default: 'text' }, // text, number, date, datetime-local, textarea, select, checkbox
  required: { type: Boolean, default: false },
  error: { type: String, default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  span2: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  maxlength: { type: [String, Number], default: undefined },
});
defineEmits(['update:modelValue']);
</script>

<template>
  <div v-if="type === 'checkbox'" class="flex items-center" :class="{ 'sm:col-span-2': span2 }">
    <input
      type="checkbox"
      :checked="modelValue"
      @change="$emit('update:modelValue', $event.target.checked)"
      class="h-5 w-5 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
    />
    <span class="ml-3 text-sm font-semibold text-gray-700">{{ label }}</span>
  </div>

  <div v-else :class="{ 'sm:col-span-2': span2 }">
    <label class="block text-sm font-semibold text-gray-700 mb-2">
      {{ label }}<span v-if="required" class="text-red-500"> *</span>
    </label>

    <select
      v-if="type === 'select'"
      :value="modelValue ?? ''"
      @change="$emit('update:modelValue', $event.target.value)"
      :class="INPUT_CLASS"
    >
      <option value="">-- Select --</option>
      <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
    </select>

    <textarea
      v-else-if="type === 'textarea'"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      rows="3"
      :class="INPUT_CLASS"
    ></textarea>

    <input
      v-else
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :maxlength="maxlength"
      @input="$emit('update:modelValue', $event.target.value)"
      :class="INPUT_CLASS"
    />

    <p v-if="error" class="text-xs text-red-600 mt-1">{{ error }}</p>
  </div>
</template>
