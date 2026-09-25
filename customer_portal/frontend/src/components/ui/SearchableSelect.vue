<script setup>
import { ref, computed, watch } from 'vue';

const props = defineProps({
  label: { type: String, required: true },
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  placeholder: { type: String, default: 'Type to search...' },
  required: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // When true, typing a value that matches nothing in `options` is kept as
  // a literal value instead of being cleared - lets the caller accept a
  // brand-new value (e.g. a chassis not yet in inventory).
  allowCustom: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue']);

const query = ref('');
const open = ref(false);
const highlightedIndex = ref(-1);

function labelFor(value) {
  const match = props.options.find((o) => o.value === value);
  if (match) return match.label;
  return props.allowCustom ? value || '' : '';
}

// Keep the displayed text in sync when the selected value changes from
// outside this component (e.g. the form resetting after a successful
// submit) - only when it actually differs, so it never clobbers what the
// user is currently typing.
watch(
  () => props.modelValue,
  (value) => {
    const label = labelFor(value);
    if (query.value !== label) query.value = label;
  },
  { immediate: true },
);

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  const source = q ? props.options.filter((o) => o.label.toLowerCase().includes(q)) : props.options;
  return source.slice(0, 50);
});

function selectOption(option) {
  query.value = option.label;
  open.value = false;
  highlightedIndex.value = -1;
  emit('update:modelValue', option.value);
}

function onInput() {
  open.value = true;
  highlightedIndex.value = -1;
  // Typing something that no longer matches the selected option updates
  // the emitted value: cleared for a plain select, or kept as a literal
  // custom value when allowCustom lets the caller accept new entries.
  if (query.value !== labelFor(props.modelValue)) {
    emit('update:modelValue', props.allowCustom ? query.value.trim().toUpperCase() : '');
  }
}

function onFocus() {
  open.value = true;
}

function onBlur() {
  // A plain click on a dropdown item is handled via @mousedown.prevent
  // below (which fires first and keeps focus), so this delay only matters
  // for clicks fully outside the dropdown.
  setTimeout(() => {
    open.value = false;
  }, 150);
}

function onKeydown(e) {
  if (!open.value) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    highlightedIndex.value = Math.min(highlightedIndex.value + 1, filtered.value.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    highlightedIndex.value = Math.max(highlightedIndex.value - 1, 0);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const opt = filtered.value[highlightedIndex.value];
    if (opt) selectOption(opt);
  } else if (e.key === 'Escape') {
    open.value = false;
  }
}
</script>

<template>
  <div>
    <label class="block text-sm font-semibold text-gray-700 mb-2">
      {{ label }}<span v-if="required" class="text-red-500"> *</span>
    </label>
    <div class="relative">
      <input
        type="text"
        v-model="query"
        :placeholder="placeholder"
        autocomplete="off"
        @input="onInput"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
        class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
      />
      <div
        v-if="open && filtered.length"
        class="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg"
      >
        <div
          v-for="(option, index) in filtered"
          :key="option.value"
          @mousedown.prevent="selectOption(option)"
          class="px-4 py-2 text-sm cursor-pointer hover:bg-blue-50"
          :class="{ 'bg-blue-50': index === highlightedIndex }"
        >
          {{ option.label }}
        </div>
      </div>
      <div
        v-else-if="open && query.trim()"
        class="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg px-4 py-2 text-sm text-gray-500"
      >
        <template v-if="allowCustom">"{{ query }}" not found in inventory - will be added as a new sale.</template>
        <template v-else>No matching results.</template>
      </div>
    </div>
    <p v-if="error" class="text-xs text-red-600 mt-1">{{ error }}</p>
  </div>
</template>
