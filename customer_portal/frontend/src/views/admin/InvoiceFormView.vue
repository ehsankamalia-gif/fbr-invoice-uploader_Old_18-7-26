<script setup>
import { reactive, ref, computed, onMounted } from 'vue';
import { getInvoiceFormOptions, getInvoicePricePreview, createInvoice } from '../../api/invoices';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';
import { fmt } from '../../utils/format';

const loading = ref(true);
const saving = ref(false);
const errorMessage = ref('');
const result = ref(null); // the created invoice, once FBR upload has been attempted

const motorcycles = ref([]);
const nextInvoiceNumber = ref('');

const form = reactive({
  chassis_number: '',
  buyer_cnic: '',
  buyer_name: '',
  buyer_father_name: '',
  buyer_phone: '',
  buyer_address: '',
  buyer_ntn: '',
  buyer_type: 'INDIVIDUAL',
  payment_mode: 'Cash',
  sale_value: '',
  tax_rate: '',
  tax_charged: '',
  further_tax: '',
  discount: 0,
});

const motorcycleOptions = computed(() =>
  motorcycles.value.map((m) => ({
    value: m.chassis_number,
    label: `${m.chassis_number} - ${m.model_name}${m.color ? ' (' + m.color + ')' : ''}`,
  })),
);

const selectedMotorcycle = computed(() => motorcycles.value.find((m) => m.chassis_number === form.chassis_number) || null);

const totalAmount = computed(() => {
  const total = (Number(form.sale_value) || 0) + (Number(form.tax_charged) || 0) + (Number(form.further_tax) || 0);
  return fmt(total);
});

onMounted(async () => {
  const data = await getInvoiceFormOptions();
  motorcycles.value = data.motorcycles;
  nextInvoiceNumber.value = data.next_invoice_number;
  form.tax_rate = data.default_tax_rate;
  loading.value = false;
});

async function onChassisChange() {
  if (!selectedMotorcycle.value) return;
  const data = await getInvoicePricePreview(selectedMotorcycle.value.id);
  if (data.price) {
    form.sale_value = data.price.sale_value;
    form.tax_charged = data.price.tax_charged;
    form.further_tax = data.price.further_tax;
  }
}

async function submit() {
  errorMessage.value = '';
  saving.value = true;
  try {
    result.value = await createInvoice({ ...form });
  } catch (e) {
    errorMessage.value = e.response?.data?.detail || 'Failed to create invoice.';
  } finally {
    saving.value = false;
  }
}

function startNewInvoice() {
  result.value = null;
  errorMessage.value = '';
  form.chassis_number = '';
  form.buyer_cnic = '';
  form.buyer_name = '';
  form.buyer_father_name = '';
  form.buyer_phone = '';
  form.buyer_address = '';
  form.buyer_ntn = '';
  form.buyer_type = 'INDIVIDUAL';
  form.payment_mode = 'Cash';
  form.sale_value = '';
  form.tax_charged = '';
  form.further_tax = '';
  form.discount = 0;
  loading.value = true;
  getInvoiceFormOptions().then((data) => {
    motorcycles.value = data.motorcycles;
    nextInvoiceNumber.value = data.next_invoice_number;
    form.tax_rate = data.default_tax_rate;
    loading.value = false;
  });
}
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-file-invoice mr-3"></i>Create Invoice</h1>
      <p class="text-gray-600">Create a sales invoice for one motorcycle and upload it to FBR.</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <!-- Result panel: shown once the invoice has been created and FBR upload attempted -->
    <div v-else-if="result" class="bg-white rounded-xl p-8 card-shadow max-w-2xl">
      <div v-if="result.sync_status === 'SYNCED'" class="text-center">
        <i class="fas fa-check-circle text-5xl text-green-500 mb-4"></i>
        <h2 class="text-2xl font-bold text-gray-800 mb-2">Invoice Fiscalized</h2>
        <p class="text-gray-600 mb-1">Invoice <strong>{{ result.invoice_number }}</strong> was uploaded to FBR successfully.</p>
        <p class="text-sm text-gray-500">FBR Invoice #: {{ result.fbr_invoice_number }}</p>
      </div>
      <div v-else class="text-center">
        <i class="fas fa-exclamation-triangle text-5xl text-yellow-500 mb-4"></i>
        <h2 class="text-2xl font-bold text-gray-800 mb-2">Saved Locally - FBR Upload {{ result.sync_status === 'PENDING' ? 'Pending' : 'Failed' }}</h2>
        <p class="text-gray-600 mb-1">Invoice <strong>{{ result.invoice_number }}</strong> was saved, but did not fiscalize with FBR.</p>
        <p class="text-sm text-gray-500">{{ result.fbr_response_message }}</p>
      </div>
      <div class="mt-8 pt-6 border-t border-gray-100 flex justify-center gap-4">
        <router-link :to="{ name: 'admin-invoices' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
          View Invoices
        </router-link>
        <button @click="startNewInvoice" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all">
          Create Another
        </button>
      </div>
    </div>

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-4xl">
      <p class="text-sm text-gray-500 mb-6">Next invoice number: <strong>{{ nextInvoiceNumber }}</strong></p>

      <p v-if="errorMessage" class="mb-6 p-4 bg-red-50 text-red-700 rounded-lg text-sm">{{ errorMessage }}</p>

      <form @submit.prevent="submit">
        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Motorcycle</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <FormField
            label="Chassis Number" type="select" required
            v-model="form.chassis_number" :options="motorcycleOptions"
            @update:modelValue="onChassisChange"
          />
        </div>

        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Buyer</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <FormField label="CNIC" required v-model="form.buyer_cnic" />
          <FormField label="Name" v-model="form.buyer_name" />
          <FormField label="Father Name" v-model="form.buyer_father_name" />
          <FormField label="NTN" v-model="form.buyer_ntn" />
          <FormField label="Phone" v-model="form.buyer_phone" />
          <FormField label="Address" v-model="form.buyer_address" />
          <FormField
            label="Buyer Type" type="select" v-model="form.buyer_type"
            :options="[{ value: 'INDIVIDUAL', label: 'Individual' }, { value: 'DEALER', label: 'Dealer' }]"
          />
          <FormField
            label="Payment Mode" type="select" v-model="form.payment_mode"
            :options="[
              { value: 'Cash', label: 'Cash' }, { value: 'Card', label: 'Card' },
              { value: 'Gift Voucher', label: 'Gift Voucher' }, { value: 'Loyalty Card', label: 'Loyalty Card' },
              { value: 'Mixed', label: 'Mixed' }, { value: 'Cheque', label: 'Cheque' },
            ]"
          />
        </div>

        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Pricing</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <FormField label="Sale Value (excl. tax)" type="number" required v-model="form.sale_value" />
          <FormField label="Tax Rate (%)" type="number" v-model="form.tax_rate" />
          <FormField label="Tax Charged" type="number" v-model="form.tax_charged" />
          <FormField label="Further Tax" type="number" v-model="form.further_tax" />
          <FormField label="Discount" type="number" v-model="form.discount" />
        </div>

        <p class="text-lg font-semibold text-gray-800 mb-6">Total Amount: Rs. {{ totalAmount }}</p>

        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-invoices' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button type="submit" :disabled="saving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            <i class="fas fa-paper-plane mr-2"></i>{{ saving ? 'Uploading to FBR...' : 'Create & Upload' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
