<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getPortalAccount, createPortalAccount, updatePortalAccount, getEligibleCustomers, getCustomerOptions } from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({ customer: '', phone_number: '', is_active: true });
const errors = ref({});
const saving = ref(false);
const loading = ref(true);
const customerOptions = ref([]);

onMounted(async () => {
  if (isEdit.value) {
    const [data, customers] = await Promise.all([getPortalAccount(route.params.id), getCustomerOptions()]);
    Object.assign(form, data);
    customerOptions.value = customers.map((c) => ({ value: c.id, label: c.name }));
  } else {
    const eligible = await getEligibleCustomers();
    customerOptions.value = eligible.map((c) => ({ value: c.id, label: `${c.name}${c.phone ? ' - ' + c.phone : ''}` }));
  }
  loading.value = false;
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updatePortalAccount(route.params.id, form);
    } else {
      await createPortalAccount(form.customer);
    }
    router.push({ name: 'admin-portal-accounts' });
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
      <router-link :to="{ name: 'admin-portal-accounts' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back to Portal Accounts
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-user-shield mr-3"></i>{{ isEdit ? 'Edit Portal Account' : 'Create Portal Account' }}
      </h1>
      <p class="text-gray-600">{{ isEdit ? 'Update this customer portal login' : 'Create a new customer portal account' }}</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-2xl">
      <form @submit.prevent="submit">
        <div class="mb-6">
          <FormField
            label="Customer" type="select" required v-model="form.customer"
            :options="customerOptions" :error="errors.customer?.[0]"
          />
          <p v-if="!isEdit" class="text-sm text-gray-500 mt-2">
            <i class="fas fa-info-circle mr-1"></i>Only customers with credit sales and no existing portal account are shown here.
          </p>
        </div>

        <template v-if="isEdit">
          <div class="mb-6">
            <FormField label="Phone Number (Username)" required v-model="form.phone_number" :error="errors.phone_number?.[0]" />
          </div>
          <div class="mb-6">
            <FormField label="Active" type="checkbox" v-model="form.is_active" />
          </div>
        </template>

        <div v-else class="bg-blue-50 rounded-lg p-4 mb-6">
          <h5 class="font-semibold text-blue-800 mb-2"><i class="fas fa-info-circle mr-2"></i>Account Details</h5>
          <ul class="text-sm text-blue-700 space-y-1">
            <li><i class="fas fa-check mr-2"></i>Username: Customer's phone number</li>
            <li><i class="fas fa-check mr-2"></i>Default password: <span class="font-mono bg-blue-100 px-2 py-0.5 rounded">123456789</span></li>
            <li><i class="fas fa-check mr-2"></i>Account will be active by default</li>
          </ul>
        </div>

        <div class="flex justify-end space-x-4">
          <router-link :to="{ name: 'admin-portal-accounts' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
            Cancel
          </router-link>
          <button type="submit" :disabled="saving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            <i class="fas fa-check mr-2"></i>{{ saving ? 'Saving...' : (isEdit ? 'Save' : 'Create Account') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
