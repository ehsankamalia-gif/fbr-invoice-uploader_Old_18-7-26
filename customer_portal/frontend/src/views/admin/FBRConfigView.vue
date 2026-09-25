<script setup>
import { reactive, ref, onMounted } from 'vue';
import { getFbrConfig, updateFbrConfig, activateFbrEnvironment } from '../../api/fbrConfig';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const activeEnv = ref(null);
const saving = reactive({ sandbox: false, production: false });
const activating = reactive({ sandbox: false, production: false });
const messages = reactive({ sandbox: '', production: '' });
const errors = reactive({ sandbox: {}, production: {} });

function blankForm() {
  return {
    api_base_url: '', pos_id: '', usin: '', auth_token: '', secret_key: '',
    tax_rate: 18, invoice_type: 'Standard', discount: 0, pos_fee: 1,
    pct_code: '8711.2010', item_code: '', item_name: '', business_name: 'Ehsan Trader',
  };
}

const forms = reactive({ sandbox: blankForm(), production: blankForm() });

const invoiceTypeOptions = [
  { value: 'Standard', label: 'Standard (New)' },
  { value: 'Debit Note', label: 'Debit Note' },
  { value: 'Credit Note', label: 'Credit Note' },
  { value: '3rd Schedule New', label: '3rd Schedule New' },
  { value: '3rd Schedule Credit', label: '3rd Schedule Credit' },
];

async function load() {
  loading.value = true;
  const data = await getFbrConfig();
  activeEnv.value = data.active;
  forms.sandbox = data.sandbox ? { ...blankForm(), ...data.sandbox } : blankForm();
  forms.production = data.production ? { ...blankForm(), ...data.production } : blankForm();
  loading.value = false;
}

async function save(envKey) {
  const environment = envKey.toUpperCase();
  errors[envKey] = {};
  messages[envKey] = '';
  saving[envKey] = true;
  try {
    const data = await updateFbrConfig(environment, forms[envKey]);
    forms[envKey] = { ...forms[envKey], ...data };
    messages[envKey] = 'Saved.';
  } catch (e) {
    errors[envKey] = e.response?.data || {};
    messages[envKey] = e.response?.data?.detail || 'Failed to save.';
  } finally {
    saving[envKey] = false;
  }
}

async function activate(envKey) {
  const environment = envKey.toUpperCase();
  if (!confirm(`Set ${environment} as the ACTIVE FBR environment? Both the desktop app and this portal will immediately start using it for new invoice uploads.`)) return;
  activating[envKey] = true;
  try {
    await activateFbrEnvironment(environment);
    await load();
  } catch (e) {
    messages[envKey] = e.response?.data?.detail || 'Failed to activate.';
  } finally {
    activating[envKey] = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-cog mr-3"></i>FBR Configuration</h1>
      <p class="text-gray-600">Shared with the desktop app - changes here affect both apps immediately.</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div v-for="envKey in ['sandbox', 'production']" :key="envKey" class="bg-white rounded-xl p-8 card-shadow">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-xl font-bold text-gray-800 capitalize">{{ envKey }}</h2>
          <span
            v-if="activeEnv === envKey.toUpperCase()"
            class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
          >
            <i class="fas fa-check-circle mr-1"></i>Active
          </span>
          <button
            v-else
            @click="activate(envKey)"
            :disabled="activating[envKey]"
            class="px-4 py-2 text-sm bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition disabled:opacity-60"
          >
            {{ activating[envKey] ? 'Activating...' : 'Set Active' }}
          </button>
        </div>

        <p v-if="messages[envKey]" class="mb-4 p-3 bg-blue-50 text-blue-700 rounded-lg text-sm">{{ messages[envKey] }}</p>

        <form @submit.prevent="save(envKey)">
          <div class="grid grid-cols-1 gap-4">
            <FormField label="API Base URL" required v-model="forms[envKey].api_base_url" :error="errors[envKey].api_base_url?.[0]" />
            <FormField label="POS ID" v-model="forms[envKey].pos_id" :error="errors[envKey].pos_id?.[0]" />
            <FormField label="USIN (invoice number prefix)" v-model="forms[envKey].usin" :error="errors[envKey].usin?.[0]" />
            <FormField label="Auth Token" v-model="forms[envKey].auth_token" :error="errors[envKey].auth_token?.[0]" />
            <FormField label="Secret Key (HMAC signing, optional)" v-model="forms[envKey].secret_key" :error="errors[envKey].secret_key?.[0]" />
            <div class="grid grid-cols-2 gap-4">
              <FormField label="Tax Rate (%)" type="number" v-model="forms[envKey].tax_rate" :error="errors[envKey].tax_rate?.[0]" />
              <FormField label="POS Fee" type="number" v-model="forms[envKey].pos_fee" :error="errors[envKey].pos_fee?.[0]" />
            </div>
            <FormField label="Invoice Type" type="select" v-model="forms[envKey].invoice_type" :options="invoiceTypeOptions" :error="errors[envKey].invoice_type?.[0]" />
            <FormField label="Discount (%)" type="number" v-model="forms[envKey].discount" :error="errors[envKey].discount?.[0]" />
            <FormField label="PCT Code" v-model="forms[envKey].pct_code" :error="errors[envKey].pct_code?.[0]" />
            <FormField label="Item Code" v-model="forms[envKey].item_code" :error="errors[envKey].item_code?.[0]" />
            <FormField label="Item Name" v-model="forms[envKey].item_name" :error="errors[envKey].item_name?.[0]" />
            <FormField label="Business Name" v-model="forms[envKey].business_name" :error="errors[envKey].business_name?.[0]" />
          </div>

          <div class="flex justify-end mt-6 pt-6 border-t border-gray-100">
            <button type="submit" :disabled="saving[envKey]" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
              {{ saving[envKey] ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
