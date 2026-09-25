<script setup>
import { reactive, ref, onMounted } from 'vue';
import { getCompanies, createCompany, updateCompany, activateCompany } from '../../api/companies';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const companies = ref([]);
const saving = reactive({});
const activating = reactive({});
const messages = reactive({});
const errors = reactive({});

const showAddForm = ref(false);
const addSaving = ref(false);
const addError = ref('');

function blankForm() {
  return { name: '', address: '', phone: '', email: '', ntn: '', cnic: '' };
}

const addForm = reactive(blankForm());

async function load() {
  loading.value = true;
  companies.value = await getCompanies();
  loading.value = false;
}

async function save(company) {
  errors[company.id] = {};
  messages[company.id] = '';
  saving[company.id] = true;
  try {
    const data = await updateCompany(company.id, company);
    Object.assign(company, data);
    messages[company.id] = 'Saved.';
  } catch (e) {
    errors[company.id] = e.response?.data || {};
    messages[company.id] = e.response?.data?.detail || 'Failed to save.';
  } finally {
    saving[company.id] = false;
  }
}

async function activate(company) {
  if (!confirm(`Set "${company.name}" as the ACTIVE company? Both the desktop app and this portal will immediately show only this company's records.`)) return;
  activating[company.id] = true;
  try {
    await activateCompany(company.id);
    await load();
  } catch (e) {
    messages[company.id] = e.response?.data?.detail || 'Failed to activate.';
  } finally {
    activating[company.id] = false;
  }
}

async function addCompany() {
  addError.value = '';
  if (!addForm.name.trim()) {
    addError.value = 'Company name is required.';
    return;
  }
  addSaving.value = true;
  try {
    await createCompany(addForm);
    Object.assign(addForm, blankForm());
    showAddForm.value = false;
    await load();
  } catch (e) {
    addError.value = e.response?.data?.name?.[0] || e.response?.data?.detail || 'Failed to add company.';
  } finally {
    addSaving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-8 flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-gray-800 mb-2"><i class="fas fa-building mr-3"></i>Companies</h1>
        <p class="text-gray-600">Only the active company's records show up across the desktop app and this portal.</p>
      </div>
      <button
        @click="showAddForm = !showAddForm"
        class="px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all"
      >
        <i class="fas fa-plus mr-2"></i>Add Company
      </button>
    </div>

    <div v-if="showAddForm" class="bg-white rounded-xl p-8 card-shadow mb-6">
      <h2 class="text-xl font-bold text-gray-800 mb-6">New Company</h2>
      <p v-if="addError" class="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{{ addError }}</p>
      <form @submit.prevent="addCompany">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField label="Company Name" required v-model="addForm.name" />
          <FormField label="Address" v-model="addForm.address" />
          <FormField label="Mobile Number" v-model="addForm.phone" />
          <FormField label="Email" type="text" v-model="addForm.email" />
          <FormField label="NTN" v-model="addForm.ntn" />
          <FormField label="CNIC" v-model="addForm.cnic" />
        </div>
        <div class="flex justify-end gap-3 mt-6 pt-6 border-t border-gray-100">
          <button type="button" @click="showAddForm = false" class="px-6 py-3 bg-gray-100 text-gray-700 font-semibold rounded-lg hover:bg-gray-200 transition">
            Cancel
          </button>
          <button type="submit" :disabled="addSaving" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
            {{ addSaving ? 'Adding...' : 'Add Company' }}
          </button>
        </div>
      </form>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div v-for="company in companies" :key="company.id" class="bg-white rounded-xl p-8 card-shadow">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-xl font-bold text-gray-800">{{ company.name }}</h2>
          <span
            v-if="company.is_active"
            class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
          >
            <i class="fas fa-check-circle mr-1"></i>Active
          </span>
          <button
            v-else
            @click="activate(company)"
            :disabled="activating[company.id]"
            class="px-4 py-2 text-sm bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition disabled:opacity-60"
          >
            {{ activating[company.id] ? 'Activating...' : 'Set Active' }}
          </button>
        </div>

        <p v-if="messages[company.id]" class="mb-4 p-3 bg-blue-50 text-blue-700 rounded-lg text-sm">{{ messages[company.id] }}</p>

        <form @submit.prevent="save(company)">
          <div class="grid grid-cols-1 gap-4">
            <FormField label="Company Name" required v-model="company.name" :error="errors[company.id]?.name?.[0]" />
            <FormField label="Address" v-model="company.address" :error="errors[company.id]?.address?.[0]" />
            <FormField label="Mobile Number" v-model="company.phone" :error="errors[company.id]?.phone?.[0]" />
            <FormField label="Email" v-model="company.email" :error="errors[company.id]?.email?.[0]" />
            <FormField label="NTN" v-model="company.ntn" :error="errors[company.id]?.ntn?.[0]" />
            <FormField label="CNIC" v-model="company.cnic" :error="errors[company.id]?.cnic?.[0]" />
          </div>

          <div class="flex justify-end mt-6 pt-6 border-t border-gray-100">
            <button type="submit" :disabled="saving[company.id]" class="px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-60">
              {{ saving[company.id] ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
