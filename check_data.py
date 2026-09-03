import json
with open('captured_forms.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get the main customer profile page
if 'https://dealers.ahlportal.com/dealersv2/dealers/customer_profile' in data['pages']:
    page = data['pages']['https://dealers.ahlportal.com/dealersv2/dealers/customer_profile']
    print('Last updated:', page['last_updated'])
    print('Fields captured:', len(page['fields']))
    print('Key fields:')
    for field in ['#txt_chassis_no', '#txt_engine_no', '#txt_full_name', '#txt_address', '#txt_cell_no']:
        if field in page['fields']:
            print('  %s: %r' % (field, page['fields'][field]['value']))
