<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getProductModel, createProductModel, updateProductModel } from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({ model_name: '', make: 'Honda', engine_capacity: '', pct_code: '', item_code: '' });
const errors = ref({});
const saving = ref(false);
const loading = ref(isEdit.value);

onMounted(async () => {
  if (isEdit.value) {
    Object.assign(form, await getProductModel(route.params.id));
    loading.value = false;
  }
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateProductModel(route.params.id, form);
    } else {
      await createProductModel(form);
    }
    router.push({ name: 'admin-manage-product-models' });
  } catch (e) {
    errors.value = e.response?.data || {};
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div>
    <div class="mb-8">
      <router-link :to="{ name: 'admin-manage-product-models' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-cogs mr-3"></i>{{ isEdit ? 'Edit Product Model' : 'Add Product Model' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-4xl">
      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <FormField label="Model Name" required v-model="form.model_name" :error="errors.model_name?.[0]" />
          <FormField label="Make" v-model="form.make" :error="errors.make?.[0]" />
          <FormField label="Engine Capacity" v-model="form.engine_capacity" :error="errors.engine_capacity?.[0]" />
          <FormField label="PCT Code" v-model="form.pct_code" :error="errors.pct_code?.[0]" />
          <FormField label="Item Code" v-model="form.item_code" :error="errors.item_code?.[0]" />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-manage-product-models' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button type="submit" :disabled="saving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            <i class="fas fa-check mr-2"></i>{{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
