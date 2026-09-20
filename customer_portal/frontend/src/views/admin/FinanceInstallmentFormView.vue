<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  getFinanceInstallment, createFinanceInstallment, updateFinanceInstallment,
  getCustomerOptions, getFinanceSaleOptions,
} from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({
  payment_id: '', sale: '', customer: '', paid_amount: 0, payment_date: '',
  payment_method: 'Cash', reference_no: '', notes: '', loan_id: '', installment_no: '',
  due_date: '', principal_due: 0, interest_due: 0, fees_due: 0, total_due: 0,
  late_fee_accrued: 0, late_fee_last_calculated_at: '', status: 'PAID',
  paid_principal: 0, paid_interest: 0, paid_fees: 0, paid_total: 0, paid_at: '',
});
const errors = ref({});
const saving = ref(false);
const loading = ref(true);
const customerOptions = ref([]);
const saleOptions = ref([]);

function dt(v) {
  return v ? v.slice(0, 16) : '';
}

onMounted(async () => {
  const [customers, sales] = await Promise.all([getCustomerOptions(), getFinanceSaleOptions()]);
  customerOptions.value = customers.map((c) => ({ value: c.id, label: c.name }));
  saleOptions.value = sales.map((s) => ({ value: s.id, label: `${s.sale_id} - ${s.customer_name}` }));

  if (isEdit.value) {
    const data = await getFinanceInstallment(route.params.id);
    Object.assign(form, data);
    form.payment_date = dt(form.payment_date);
    form.due_date = dt(form.due_date);
    form.late_fee_last_calculated_at = dt(form.late_fee_last_calculated_at);
    form.paid_at = dt(form.paid_at);
  }
  loading.value = false;
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateFinanceInstallment(route.params.id, form);
    } else {
      await createFinanceInstallment(form);
    }
    router.push({ name: 'admin-manage-finance-installments' });
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
      <router-link :to="{ name: 'admin-manage-finance-installments' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-hand-holding-usd mr-3"></i>{{ isEdit ? 'Edit Installment' : 'Add Finance Installment' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-5xl">
      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <FormField label="Payment ID" required v-model="form.payment_id" :error="errors.payment_id?.[0]" />
          <FormField label="Sale" type="select" required v-model="form.sale" :options="saleOptions" :error="errors.sale?.[0]" />
          <FormField label="Customer" type="select" required v-model="form.customer" :options="customerOptions" :error="errors.customer?.[0]" />
          <FormField label="Paid Amount" type="number" required v-model="form.paid_amount" :error="errors.paid_amount?.[0]" />
          <FormField label="Payment Date" type="datetime-local" v-model="form.payment_date" :error="errors.payment_date?.[0]" />
          <FormField label="Payment Method" v-model="form.payment_method" :error="errors.payment_method?.[0]" />
          <FormField label="Reference No" v-model="form.reference_no" :error="errors.reference_no?.[0]" />
          <FormField label="Loan ID" type="number" v-model="form.loan_id" :error="errors.loan_id?.[0]" />
          <FormField label="Installment No" type="number" v-model="form.installment_no" :error="errors.installment_no?.[0]" />
          <FormField label="Due Date" type="datetime-local" v-model="form.due_date" :error="errors.due_date?.[0]" />
          <FormField label="Principal Due" type="number" v-model="form.principal_due" :error="errors.principal_due?.[0]" />
          <FormField label="Interest Due" type="number" v-model="form.interest_due" :error="errors.interest_due?.[0]" />
          <FormField label="Fees Due" type="number" v-model="form.fees_due" :error="errors.fees_due?.[0]" />
          <FormField label="Total Due" type="number" v-model="form.total_due" :error="errors.total_due?.[0]" />
          <FormField label="Late Fee Accrued" type="number" v-model="form.late_fee_accrued" :error="errors.late_fee_accrued?.[0]" />
          <FormField label="Late Fee Last Calculated" type="datetime-local" v-model="form.late_fee_last_calculated_at" :error="errors.late_fee_last_calculated_at?.[0]" />
          <FormField
            label="Status" type="select" v-model="form.status" :error="errors.status?.[0]"
            :options="[{ value: 'PENDING', label: 'Pending' }, { value: 'PAID', label: 'Paid' }, { value: 'PARTIAL', label: 'Partial' }]"
          />
          <FormField label="Paid Principal" type="number" v-model="form.paid_principal" :error="errors.paid_principal?.[0]" />
          <FormField label="Paid Interest" type="number" v-model="form.paid_interest" :error="errors.paid_interest?.[0]" />
          <FormField label="Paid Fees" type="number" v-model="form.paid_fees" :error="errors.paid_fees?.[0]" />
          <FormField label="Paid Total" type="number" v-model="form.paid_total" :error="errors.paid_total?.[0]" />
          <FormField label="Paid At" type="datetime-local" v-model="form.paid_at" :error="errors.paid_at?.[0]" />
          <FormField label="Notes" type="textarea" v-model="form.notes" :error="errors.notes?.[0]" span2 />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-manage-finance-installments' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
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
