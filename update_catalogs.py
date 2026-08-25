import json

base_plans = [
    {
        'id_suffix': '40M',
        'name_prefix': 'Basic',
        'speed_mbps': 40,
        'price_inr': 499,
        'type': 'fiber',
        'reason_template': '40 Mbps plan ideal for basic web browsing and standard streaming.',
        'ott': []
    },
    {
        'id_suffix': '100M',
        'name_prefix': 'Standard',
        'speed_mbps': 100,
        'price_inr': 799,
        'type': 'fiber',
        'reason_template': '100 Mbps fiber for HD streaming and multiple devices.',
        'ott': ['Disney+ Hotstar']
    },
    {
        'id_suffix': '200M',
        'name_prefix': 'Entertainment',
        'speed_mbps': 200,
        'price_inr': 999,
        'type': 'fiber',
        'reason_template': '200 Mbps plan with OTT benefits for family entertainment.',
        'ott': ['Disney+ Hotstar', 'Amazon Prime', 'Zee5']
    },
    {
        'id_suffix': '300M',
        'name_prefix': 'Professional',
        'speed_mbps': 300,
        'price_inr': 1499,
        'type': 'fiber',
        'reason_template': '300 Mbps high-speed plan with premium OTT bundles.',
        'ott': ['Netflix Basic', 'Amazon Prime', 'Disney+ Hotstar', 'SonyLIV', 'Zee5']
    },
    {
        'id_suffix': '500M',
        'name_prefix': 'Max',
        'speed_mbps': 500,
        'price_inr': 2499,
        'type': 'fiber',
        'reason_template': '500 Mbps extreme speed for large households and 4K streaming.',
        'ott': ['Netflix Standard', 'Amazon Prime', 'Disney+ Hotstar Premium', 'SonyLIV', 'Zee5']
    },
    {
        'id_suffix': '1G',
        'name_prefix': 'Infinity',
        'speed_mbps': 1000,
        'price_inr': 3999,
        'type': 'fiber',
        'reason_template': '1 Gbps Ultra Giga Speed for intensive gaming, 4K streaming, and smart homes.',
        'ott': ['Netflix Premium 4K', 'Amazon Prime', 'Disney+ Hotstar Premium', 'SonyLIV', 'Zee5', 'Apple TV+']
    }
]

with open('data/regional_plans_catalog.json', 'r') as f:
    data = json.load(f)

for region in data['circles']:
    region_code = region[:3].upper().replace(' ', '')
    new_plans = []
    for p in base_plans:
        new_plans.append({
            'plan_id': f"PLN-{region_code}-{p['id_suffix']}",
            'name': f"{region} {p['name_prefix']} {p['id_suffix']}",
            'speed_mbps': p['speed_mbps'],
            'price_inr': p['price_inr'],
            'type': p['type'],
            'reason': p['reason_template'].replace('plan', f'plan for {region}'),
            'ott_bundle': p['ott']
        })
    data['circles'][region] = new_plans

with open('data/regional_plans_catalog.json', 'w') as f:
    json.dump(data, f, indent=2)

generic_plans = []
for i, p in enumerate(base_plans):
    generic_plans.append({
        'plan_id': f'PLAN-0{i}',
        'name': f"{p['name_prefix']} {p['id_suffix']}",
        'speed_mbps': p['speed_mbps'],
        'price_inr': p['price_inr'],
        'type': p['type'],
        'min_speed_required': p['speed_mbps'] // 2,
        'ott_bundle': p['ott'],
        'description': p['reason_template']
    })

with open('data/plans_catalog.json', 'r') as f:
    cat_data = json.load(f)
cat_data['plans'] = generic_plans

with open('data/plans_catalog.json', 'w') as f:
    json.dump(cat_data, f, indent=2)

print('Done')
