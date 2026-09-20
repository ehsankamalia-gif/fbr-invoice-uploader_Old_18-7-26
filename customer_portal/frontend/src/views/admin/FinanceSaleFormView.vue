<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getFinanceSale, createFinanceSale, updateFinanceSale, getCustomerOptions } from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({
  sale_id: '', customer: '', customer_name: '', chassis_no: '', engine_no: '', model: '',
  cash_price: 0, credit_price: 0, down_payment: 0, down_payment_method: 'Cash',
  duration_months: 0, duration_days: 0, installment_amount: 0,
  sale_date: '', due_date: '', remaining_balance: 0, status: 'ACTIVE',
  credit_type: 'Advanced Separate Finance', notes: '',
});
const errors = ref({});
const saving = ref(false);
const loading = ref(true);
const customerOptions = ref([]);

onMounted(async () => {
  const customers = await getCustomerOptions();
  customerOptions.value = customers.map((c) => ({ value: c.id, label: c.name }));

  if (isEdit.value) {
    const data = await getFinanceSale(route.params.id);
    Object.assign(form, data);
    if (form.sale_date) form.sale_date = form.sale_date.slice(0, 16);
    if (form.due_date) form.due_date = form.due_date.slice(0, 16);
  }
  loading.value = false;
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateFinanceSale(route.params.id, form);
    } else {
      await createFinanceSale(form);
    }
    router.push({ name: 'admin-sales' });
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
      <router-link :to="{ name: 'admin-sales' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-shopping-cart mr-3"></i>{{ isEdit ? 'Edit Sale' : 'Add Finance Credit Sale' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-5xl">
      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <FormField label="Sale ID" required v-model="form.sale_id" :error="errors.sale_id?.[0]" />
          <FormField label="Customer" type="select" required v-model="form.customer" :options="customerOptions" :error="errors.customer?.[0]" />
          <FormField label="Customer Name" required v-model="form.customer_name" :error="errors.customer_name?.[0]" />
          <FormField label="Chassis No" required v-model="form.chassis_no" :error="errors.chassis_no?.[0]" />
          <FormField label="Engine No" v-model="form.engine_no" :error="errors.engine_no?.[0]" />
          <FormField label="Model" v-model="form.model" :error="errors.model?.[0]" />
          <FormField label="Cash Price" type="number" v-model="form.cash_price" :error="errors.cash_price?.[0]" />
          <FormField label="Credit Price" type="number" v-model="form.credit_price" :error="errors.credit_price?.[0]" />
          <FormField label="Down Payment" type="number" v-model="form.down_payment" :error="errors.down_payment?.[0]" />
          <FormField label="Down Payment Method" v-model="form.down_payment_method" :error="errors.down_payment_method?.[0]" />
          <FormField label="Duration (Months)" type="number" v-model="form.duration_months" :error="errors.duration_months?.[0]" />
          <FormField label="Duration (Days)" type="number" v-model="form.duration_days" :error="errors.duration_days?.[0]" />
          <FormField label="Installment Amount" type="number" v-model="form.installment_amount" :error="errors.installment_amount?.[0]" />
          <FormField label="Sale Date" type="datetime-local" v-model="form.sale_date" :error="errors.sale_date?.[0]" />
          <FormField label="Due Date" type="datetime-local" v-model="form.due_date" :error="errors.due_date?.[0]" />
          <FormField label="Remaining Balance" type="number" v-model="form.remaining_balance" :error="errors.remaining_balance?.[0]" />
          <FormField
            label="Status" type="select" v-model="form.status" :error="errors.status?.[0]"
            :options="[{ value: 'ACTIVE', label: 'Active' }, { value: 'CLOSED', label: 'Closed' }, { value: 'OVERDUE', label: 'Overdue' }]"
          />
          <FormField label="Credit Type" v-model="form.credit_type" :error="errors.credit_type?.[0]" />
          <FormField label="Notes" type="textarea" v-model="form.notes" :error="errors.notes?.[0]" span2 />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-sales' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
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
