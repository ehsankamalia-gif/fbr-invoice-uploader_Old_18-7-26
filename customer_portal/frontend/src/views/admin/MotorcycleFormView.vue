<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getMotorcycle, createMotorcycle, updateMotorcycle, listProductModels } from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({
  product_model: '', vin: '', chassis_number: '', engine_number: '', year: new Date().getFullYear(),
  color: '', cost_price: '', sale_price: '', status: 'IN_STOCK', purchase_date: '',
});
const errors = ref({});
const saving = ref(false);
const loading = ref(true);
const productModelOptions = ref([]);

onMounted(async () => {
  const productModels = await listProductModels();
  productModelOptions.value = productModels.map((pm) => ({ value: pm.id, label: pm.model_name }));

  if (isEdit.value) {
    const data = await getMotorcycle(route.params.id);
    Object.assign(form, data);
    if (form.purchase_date) form.purchase_date = form.purchase_date.slice(0, 16);
  }
  loading.value = false;
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateMotorcycle(route.params.id, form);
    } else {
      await createMotorcycle(form);
    }
    router.push({ name: 'admin-inventory' });
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
      <router-link :to="{ name: 'admin-inventory' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-motorcycle mr-3"></i>{{ isEdit ? 'Edit Motorcycle' : 'Add Motorcycle' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-4xl">
      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <FormField label="Product Model" type="select" required v-model="form.product_model" :options="productModelOptions" :error="errors.product_model?.[0]" />
          <FormField label="VIN" v-model="form.vin" :error="errors.vin?.[0]" />
          <FormField label="Chassis Number" required v-model="form.chassis_number" :error="errors.chassis_number?.[0]" />
          <FormField label="Engine Number" required v-model="form.engine_number" :error="errors.engine_number?.[0]" />
          <FormField label="Year" type="number" required v-model="form.year" :error="errors.year?.[0]" />
          <FormField label="Color" v-model="form.color" :error="errors.color?.[0]" />
          <FormField label="Cost Price" type="number" required v-model="form.cost_price" :error="errors.cost_price?.[0]" />
          <FormField label="Sale Price" type="number" required v-model="form.sale_price" :error="errors.sale_price?.[0]" />
          <FormField
            label="Status" type="select" v-model="form.status" :error="errors.status?.[0]"
            :options="[{ value: 'IN_STOCK', label: 'In Stock' }, { value: 'SOLD', label: 'Sold' }]"
          />
          <FormField label="Purchase Date" type="datetime-local" v-model="form.purchase_date" :error="errors.purchase_date?.[0]" />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-inventory' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
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
