<script setup>
import { reactive, ref, computed, onMounted } from 'vue';
import { getInvoiceFormOptions, getInvoicePricePreview, getInvoicePricePreviewByModel, createInvoice, lookupCustomerByCnic } from '../../api/invoices';
import FormField from '../../components/ui/FormField.vue';
import SearchableSelect from '../../components/ui/SearchableSelect.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';
import { fmt } from '../../utils/format';

const loading = ref(true);
const saving = ref(false);
const errorMessage = ref(''); // generic, not tied to a specific field
const errors = ref({}); // DRF-style { field: [message] }, shown under each input
const result = ref(null); // the created invoice, once FBR upload has been attempted

const motorcycles = ref([]);
const productModels = ref([]);
const knownColors = ref([]);
const nextInvoiceNumber = ref('');
const fbrEnvironment = ref('');

const form = reactive({
  chassis_number: '',
  engine_number: '',
  product_model_id: '',
  color: '',
  buyer_cnic: '',
  buyer_name: '',
  buyer_father_name: '',
  buyer_phone: '',
  buyer_address: '',
  buyer_ntn: '',
  buyer_type: 'INDIVIDUAL',
  payment_mode: 'Cash',
  quantity: 1,
  sale_value: '',
  tax_rate: '',
  tax_charged: '',
  further_tax: '',
  discount: 0,
});

// Input formatting: CNIC as 33302-0085847-5 (exactly 13 digits), phone as
// plain digits (exactly 11), name/father name restricted to letters and
// spaces only. Applied synchronously in each field's own update handler
// (rather than a watcher) so there's no reactivity-timing gap where an
// invalid character could flash through.
function formatCnicValue(raw) {
  const digits = (raw || '').replace(/\D/g, '').slice(0, 13);
  if (digits.length > 12) return `${digits.slice(0, 5)}-${digits.slice(5, 12)}-${digits.slice(12)}`;
  if (digits.length > 5) return `${digits.slice(0, 5)}-${digits.slice(5)}`;
  return digits;
}
function formatPhoneValue(raw) {
  return (raw || '').replace(/\D/g, '').slice(0, 11);
}
function formatNameValue(raw) {
  return (raw || '').replace(/[^A-Za-z ]/g, '');
}
// Guards the lookup below so it fires once per distinct completed CNIC,
// not on every keystroke after that (mirrors the desktop app's
// _last_cnic_autofill guard in _on_invoice_cnic_changed).
let lastCnicLookup = null;

async function onCnicInput(val) {
  const formatted = formatCnicValue(val);
  form.buyer_cnic = formatted;

  const digits = formatted.replace(/\D/g, '');
  if (digits.length !== 13) {
    lastCnicLookup = null;
    return;
  }
  if (formatted === lastCnicLookup) return;
  lastCnicLookup = formatted;

  const data = await lookupCustomerByCnic(formatted);
  // The user may have kept typing (or cleared the field) while the lookup
  // was in flight - only apply it if this is still the current CNIC.
  if (data.customer && form.buyer_cnic === formatted) {
    const c = data.customer;
    if (c.name) form.buyer_name = c.name;
    if (c.father_name) form.buyer_father_name = c.father_name;
    if (c.phone) form.buyer_phone = formatPhoneValue(c.phone);
    if (c.address) form.buyer_address = c.address;
    if (c.type) form.buyer_type = c.type;
  }
}
function onPhoneInput(val) {
  form.buyer_phone = formatPhoneValue(val);
}
function onNameInput(val) {
  form.buyer_name = formatNameValue(val);
}
function onFatherNameInput(val) {
  form.buyer_father_name = formatNameValue(val);
}

const motorcycleOptions = computed(() =>
  motorcycles.value.map((m) => ({
    value: m.chassis_number,
    label: `${m.chassis_number} - ${m.model_name}${m.color ? ' (' + m.color + ')' : ''}`,
  })),
);

const productModelOptions = computed(() => productModels.value.map((pm) => ({ value: pm.id, label: pm.model_name })));
const colorSelectOptions = computed(() => knownColors.value.map((c) => ({ value: c, label: c })));

const selectedMotorcycle = computed(() => motorcycles.value.find((m) => m.chassis_number === form.chassis_number) || null);

// A chassis that was typed but doesn't match anything currently in
// inventory - the form falls back to manual Model/Color entry so it can
// still be sold (mirrors the desktop app's "add to inventory as SOLD" path).
const isManualChassis = computed(() => !!form.chassis_number && !selectedMotorcycle.value);

const colorOptions = computed(() =>
  selectedMotorcycle.value ? [{ value: selectedMotorcycle.value.color || '', label: selectedMotorcycle.value.color || '(none)' }] : [],
);

const totalAmount = computed(() => {
  const qty = Number(form.quantity) || 1;
  const perUnit = (Number(form.sale_value) || 0) + (Number(form.tax_charged) || 0) + (Number(form.further_tax) || 0);
  return fmt(perUnit * qty);
});

const NAME_PATTERN = /^[A-Za-z]+( [A-Za-z]+)*$/;

// Returns the first failing { field, message }, or null if everything
// required for submission is filled in and correctly formatted. Shared by
// isFormValid (drives the submit button) and submit() (shows the error
// inline if it's somehow triggered anyway, e.g. pressing Enter).
function firstValidationError() {
  if (!form.chassis_number.trim()) {
    return { field: 'chassis_number', message: 'Chassis number is required.' };
  }
  if (!form.engine_number.trim()) {
    return { field: 'engine_number', message: 'Engine number is required.' };
  }
  if (isManualChassis.value) {
    if (!form.product_model_id) return { field: 'product_model_id', message: 'Model is required.' };
    if (!form.color) return { field: 'color', message: 'Color is required.' };
  } else if (!selectedMotorcycle.value?.color) {
    return { field: 'color', message: 'This motorcycle has no color on record - update it in Inventory first.' };
  }
  const cnicDigits = form.buyer_cnic.replace(/\D/g, '');
  if (cnicDigits.length !== 13) return { field: 'buyer_cnic', message: 'CNIC must be exactly 13 digits.' };
  if (!NAME_PATTERN.test(form.buyer_name.trim())) return { field: 'buyer_name', message: 'Name is required (letters only).' };
  if (!NAME_PATTERN.test(form.buyer_father_name.trim())) return { field: 'buyer_father_name', message: 'Father name is required (letters only).' };
  if (form.buyer_phone.length !== 11) return { field: 'buyer_phone', message: 'Phone number must be exactly 11 digits.' };
  if (!form.buyer_address.trim()) return { field: 'buyer_address', message: 'Address is required.' };
  if (!(Number(form.sale_value) > 0)) return { field: 'sale_value', message: 'Sale value must be greater than zero.' };
  return null;
}

const isFormValid = computed(() => firstValidationError() === null);

onMounted(async () => {
  const data = await getInvoiceFormOptions();
  motorcycles.value = data.motorcycles;
  productModels.value = data.product_models;
  knownColors.value = data.known_colors;
  nextInvoiceNumber.value = data.next_invoice_number;
  fbrEnvironment.value = data.environment;
  form.tax_rate = data.default_tax_rate;
  loading.value = false;
});

async function onChassisChange() {
  form.product_model_id = '';
  form.color = '';
  if (!selectedMotorcycle.value) {
    form.engine_number = '';
    return;
  }
  form.engine_number = selectedMotorcycle.value.engine_number || '';
  const data = await getInvoicePricePreview(selectedMotorcycle.value.id);
  if (data.price) {
    form.sale_value = data.price.sale_value;
    form.tax_charged = data.price.tax_charged;
    form.further_tax = data.price.further_tax;
  }
}

async function onManualModelOrColorChange() {
  if (!isManualChassis.value || !form.product_model_id || !form.color) return;
  const data = await getInvoicePricePreviewByModel(form.product_model_id, form.color);
  if (data.price) {
    form.sale_value = data.price.sale_value;
    form.tax_charged = data.price.tax_charged;
    form.further_tax = data.price.further_tax;
  }
}

async function submit() {
  errorMessage.value = '';
  errors.value = {};

  const firstError = firstValidationError();
  if (firstError) {
    errors.value = { [firstError.field]: [firstError.message] };
    return;
  }

  saving.value = true;
  try {
    result.value = await createInvoice({ ...form });
  } catch (e) {
    const data = e.response?.data;
    if (data && typeof data === 'object') {
      errors.value = data;
      if (!data.detail) errorMessage.value = '';
      else errorMessage.value = data.detail;
    } else {
      errorMessage.value = 'Failed to create invoice.';
    }
  } finally {
    saving.value = false;
  }
}

function startNewInvoice() {
  result.value = null;
  errorMessage.value = '';
  errors.value = {};
  lastCnicLookup = null;
  form.chassis_number = '';
  form.engine_number = '';
  form.product_model_id = '';
  form.color = '';
  form.buyer_cnic = '';
  form.buyer_name = '';
  form.buyer_father_name = '';
  form.buyer_phone = '';
  form.buyer_address = '';
  form.buyer_ntn = '';
  form.buyer_type = 'INDIVIDUAL';
  form.payment_mode = 'Cash';
  form.quantity = 1;
  form.sale_value = '';
  form.tax_charged = '';
  form.further_tax = '';
  form.discount = 0;
  loading.value = true;
  getInvoiceFormOptions().then((data) => {
    motorcycles.value = data.motorcycles;
    productModels.value = data.product_models;
    knownColors.value = data.known_colors;
    nextInvoiceNumber.value = data.next_invoice_number;
    fbrEnvironment.value = data.environment;
    form.tax_rate = data.default_tax_rate;
    loading.value = false;
  });
}
</script>

<template>
  <div>
    <div class="mb-8 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-file-invoice mr-3"></i>Create Invoice</h1>
        <p class="text-gray-600">Create a sales invoice for one motorcycle and upload it to FBR.</p>
      </div>
      <span
        v-if="fbrEnvironment"
        class="inline-flex items-center px-4 py-2 rounded-lg text-sm font-semibold whitespace-nowrap"
        :class="fbrEnvironment === 'PRODUCTION' ? 'bg-green-100 text-green-800 border border-green-300' : 'bg-amber-100 text-amber-800 border border-amber-300'"
        title="Active FBR environment - invoices are uploaded here"
      >
        <i class="fas fa-satellite-dish mr-2"></i>FBR: {{ fbrEnvironment }}
      </span>
    </div>

    <LoadingSpinner v-if="loading" />

    <!-- Result panel: shown once the invoice has been created and FBR upload attempted -->
    <div v-else-if="result" class="bg-white rounded-xl p-8 card-shadow max-w-2xl">
      <div v-if="result.sync_status === 'SYNCED'" class="text-center">
        <i class="fas fa-check-circle text-5xl text-green-500 mb-4"></i>
        <h2 class="text-2xl font-bold text-gray-800 mb-2">Invoice Fiscalized</h2>
        <p class="text-gray-600 mb-1">Invoice <strong>{{ result.invoice_number }}</strong> was uploaded to FBR successfully.</p>
        <p class="text-sm text-gray-500 mb-4">FBR Invoice #: {{ result.fbr_invoice_number }}</p>
        <img
          v-if="result.qr_code_base64"
          :src="`data:image/png;base64,${result.qr_code_base64}`"
          alt="FBR verification QR code"
          class="mx-auto w-40 h-40 border border-gray-200 rounded-lg p-2"
        />
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
        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Buyer</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <FormField
            label="CNIC" required placeholder="33302-0085847-5" maxlength="15"
            :model-value="form.buyer_cnic" @update:modelValue="onCnicInput"
            :error="errors.buyer_cnic?.[0]"
          />
          <FormField
            label="Name" required placeholder="e.g. Muhammad Ali"
            :model-value="form.buyer_name" @update:modelValue="onNameInput"
            :error="errors.buyer_name?.[0]"
          />
          <FormField
            label="Father Name" required placeholder="e.g. Ahmed Khan"
            :model-value="form.buyer_father_name" @update:modelValue="onFatherNameInput"
            :error="errors.buyer_father_name?.[0]"
          />
          <FormField label="NTN" placeholder="e.g. 1234567-8 (optional)" v-model="form.buyer_ntn" />
          <FormField
            label="Phone" required placeholder="03021425133" maxlength="11"
            :model-value="form.buyer_phone" @update:modelValue="onPhoneInput"
            :error="errors.buyer_phone?.[0]"
          />
          <FormField
            label="Address" required placeholder="House/Street, Area, City" v-model="form.buyer_address"
            :error="errors.buyer_address?.[0]"
          />
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

        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Motorcycle</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <SearchableSelect
            label="Chassis Number" required allow-custom
            placeholder="Type full or partial chassis number..."
            v-model="form.chassis_number" :options="motorcycleOptions"
            @update:modelValue="onChassisChange"
            :error="errors.chassis_number?.[0]"
          />
          <FormField
            label="Engine Number" required placeholder="Auto-filled from chassis, or type manually"
            v-model="form.engine_number" :error="errors.engine_number?.[0]"
          />

          <template v-if="isManualChassis">
            <p class="sm:col-span-2 -mt-2 text-sm text-amber-600">
              <i class="fas fa-info-circle mr-1"></i>Chassis not found in inventory - select a Model and Color to add it as a new sale.
            </p>
            <FormField
              label="Model" type="select" required
              v-model="form.product_model_id" :options="productModelOptions"
              @update:modelValue="onManualModelOrColorChange"
              :error="errors.product_model_id?.[0]"
            />
            <FormField
              label="Color" type="select" required
              v-model="form.color" :options="colorSelectOptions"
              @update:modelValue="onManualModelOrColorChange"
              :error="errors.color?.[0]"
            />
          </template>
          <FormField
            v-else
            label="Color" type="select"
            :model-value="selectedMotorcycle ? (selectedMotorcycle.color || '') : ''"
            :options="colorOptions"
            :error="errors.color?.[0]"
          />
        </div>

        <h3 class="text-sm uppercase font-semibold text-gray-500 mb-4">Pricing</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-2">Quantity</label>
            <input
              type="text" readonly :value="form.quantity"
              class="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
            />
          </div>
          <FormField
            label="Sale Value (per unit, excl. tax)" type="number" required placeholder="0.00"
            v-model="form.sale_value" :error="errors.sale_value?.[0]"
          />
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-2">Tax Rate (%)</label>
            <input
              type="text" readonly :value="form.tax_rate"
              class="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
            />
          </div>
          <FormField label="Tax Charged (per unit)" type="number" placeholder="0.00" v-model="form.tax_charged" />
          <FormField label="Further Tax (per unit)" type="number" placeholder="0.00" v-model="form.further_tax" />
          <FormField label="Discount" type="number" placeholder="0.00" v-model="form.discount" />
        </div>

        <p class="text-lg font-semibold text-gray-800 mb-6">Total Amount: Rs. {{ totalAmount }}</p>

        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-invoices' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button
            type="submit" :disabled="saving || !isFormValid"
            :title="!isFormValid ? 'Fill in all required fields correctly first' : ''"
            class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <i class="fas fa-paper-plane mr-2"></i>{{ saving ? 'Uploading to FBR...' : 'Create & Upload' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
