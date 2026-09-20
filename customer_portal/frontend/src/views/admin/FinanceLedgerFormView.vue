<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  getFinanceLedgerEntry, createFinanceLedgerEntry, updateFinanceLedgerEntry,
  getCustomerOptions, getFinanceSaleOptions,
} from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({
  ledger_id: '', customer: '', sale: '', entry_type: 'CREDIT', description: '',
  debit: 0, credit: 0, balance: 0, entry_date: '',
});
const errors = ref({});
const saving = ref(false);
const loading = ref(true);
const customerOptions = ref([]);
const saleOptions = ref([]);

onMounted(async () => {
  const [customers, sales] = await Promise.all([getCustomerOptions(), getFinanceSaleOptions()]);
  customerOptions.value = customers.map((c) => ({ value: c.id, label: c.name }));
  saleOptions.value = sales.map((s) => ({ value: s.id, label: `${s.sale_id} - ${s.customer_name}` }));

  if (isEdit.value) {
    const data = await getFinanceLedgerEntry(route.params.id);
    Object.assign(form, data);
    if (form.entry_date) form.entry_date = form.entry_date.slice(0, 16);
  }
  loading.value = false;
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateFinanceLedgerEntry(route.params.id, form);
    } else {
      await createFinanceLedgerEntry(form);
    }
    router.push({ name: 'admin-manage-finance-ledger' });
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
      <router-link :to="{ name: 'admin-manage-finance-ledger' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-book mr-3"></i>{{ isEdit ? 'Edit Ledger Entry' : 'Add Ledger Entry' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-4xl">
      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <FormField label="Ledger ID" required v-model="form.ledger_id" :error="errors.ledger_id?.[0]" />
          <FormField label="Customer" type="select" required v-model="form.customer" :options="customerOptions" :error="errors.customer?.[0]" />
          <FormField label="Sale (optional)" type="select" v-model="form.sale" :options="saleOptions" :error="errors.sale?.[0]" />
          <FormField
            label="Entry Type" type="select" required v-model="form.entry_type" :error="errors.entry_type?.[0]"
            :options="[{ value: 'CREDIT', label: 'Credit' }, { value: 'DEBIT', label: 'Debit' }]"
          />
          <FormField label="Debit" type="number" v-model="form.debit" :error="errors.debit?.[0]" />
          <FormField label="Credit" type="number" v-model="form.credit" :error="errors.credit?.[0]" />
          <FormField label="Balance" type="number" v-model="form.balance" :error="errors.balance?.[0]" />
          <FormField label="Entry Date" type="datetime-local" v-model="form.entry_date" :error="errors.entry_date?.[0]" />
          <FormField label="Description" type="textarea" v-model="form.description" :error="errors.description?.[0]" span2 />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-manage-finance-ledger' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
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
