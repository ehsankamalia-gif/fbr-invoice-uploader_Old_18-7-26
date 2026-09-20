<script setup>
import { reactive, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getManageCustomer, createManageCustomer, updateManageCustomer } from '../../api/manage';
import FormField from '../../components/ui/FormField.vue';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const route = useRoute();
const router = useRouter();
const isEdit = computed(() => !!route.params.id);

const form = reactive({
  cnic: '', name: '', father_name: '', business_name: '', ntn: '',
  phone: '', address: '', type: 'INDIVIDUAL',
});
const errors = ref({});
const saving = ref(false);
const loading = ref(isEdit.value);

onMounted(async () => {
  if (isEdit.value) {
    Object.assign(form, await getManageCustomer(route.params.id));
    loading.value = false;
  }
});

async function submit() {
  errors.value = {};
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateManageCustomer(route.params.id, form);
    } else {
      await createManageCustomer(form);
    }
    router.push({ name: 'admin-manage-customers' });
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
      <router-link :to="{ name: 'admin-manage-customers' }" class="text-blue-500 hover:text-blue-600 mb-4 inline-flex items-center">
        <i class="fas fa-arrow-left mr-2"></i>Back
      </router-link>
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas mr-3" :class="isEdit ? 'fa-user-edit' : 'fa-user-plus'"></i>{{ isEdit ? 'Edit Customer' : 'Add Customer' }}
      </h1>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else class="bg-white rounded-xl p-8 card-shadow max-w-4xl">
      <form @submit.prevent="submit">
        <div v-if="errors.non_field_errors" class="mb-6 bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          <p v-for="(err, i) in errors.non_field_errors" :key="i">{{ err }}</p>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <FormField label="CNIC" required v-model="form.cnic" :error="errors.cnic?.[0]" />
          <FormField label="Name" required v-model="form.name" :error="errors.name?.[0]" />
          <FormField label="Father's Name" v-model="form.father_name" :error="errors.father_name?.[0]" />
          <FormField label="Business Name" v-model="form.business_name" :error="errors.business_name?.[0]" />
          <FormField label="NTN" v-model="form.ntn" :error="errors.ntn?.[0]" />
          <FormField label="Phone" v-model="form.phone" :error="errors.phone?.[0]" />
          <FormField label="Address" v-model="form.address" :error="errors.address?.[0]" span2 />
          <FormField
            label="Type" type="select" v-model="form.type" :error="errors.type?.[0]"
            :options="[{ value: 'INDIVIDUAL', label: 'Individual' }, { value: 'DEALER', label: 'Dealer' }]"
          />
        </div>
        <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-100">
          <router-link :to="{ name: 'admin-manage-customers' }" class="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300 transition">
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
