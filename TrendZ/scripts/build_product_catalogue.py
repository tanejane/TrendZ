"""Materialize manually curated Malaysian PDP facts; no network, prices or inferred INCI.

Only edit curated records after checking the linked page. Bump VERSION when facts change.
Source verification used public browser/search extracts, not a fresh package inspection.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.product_catalogue import FIELDS, normalize_ingredient

VERSION = 'my-curated-2026-10-15-v1'
VERIFIED = '2026-10-15'  # Day precision, not a fabricated retrieval time-of-day.
LOREAL = 'https://www.lorealparis.com.my/'
MAYBELLINE = 'https://www.maybelline.com.my/all-products/'
LRP = 'https://www.laroche-posay.com.my/'

HA = 'AQUA / WATER, GLYCERIN, HYDROXYETHYLPIPERA ZINE ETHANE SULFONIC ACID, SODIUM HYALURONATE, PHENOXYETHANOL, PEG-60 HYDROGENATED CASTOR OIL, ASCORBYL GLUCOSIDE, CHLORPHENESIN, HYDROXYPROPYL GUAR, SODIUM ACETYLATED HYALURONATE, XANTHAN GUM, PENTYLENE GLYCOL, SECALE CEREALE SEED EXTRACT / RYE SEED EXTRACT, DIPEPTIDE DIAMINOBUTYROYL BENZYLAMIDE DIACETATE.'
OIL_CONTROL = 'AQUA / WATER, ALCOHOL DENAT., GLYCERIN, DIPROPYLENE GLYCOL, BUTYLENE GLYCOL, NIACINAMIDE, PEG/PPG/POLYBUTYLENE GLYCOL-8/5/3 GLYCERIN, SALICYLIC ACID, HYDROXYETHYLPIPERAZINE ETHANE SULFONIC ACID, BIS-PEG-18 METHYL ETHER DIMETHYL SILANE, SODIUM HYDROXIDE, LINALOOL, GERANIOL, ZINC GLUCONATE, SCLEROTIUM GUM, ALPHA-ISOMETHYL IONONE, LECITHIN, SODIUM HYALURONATE, SILICA, PULLULAN, PHENOXYETHANOL, ADENOSINE, AMMONIUM POLYACRYLOYLDIMETHYL TAURATE, LIMONENE, TOCOPHEROL, CAPRYLOYL SALICYLIC ACID, TETRASODIUM GLUTAMATE DIACETATE, CITRONELLOL, XANTHAN GUM, PEG-60 HYDROGENATED CASTOR OIL, PARFUM / FRAGRANCE.'
B5 = 'AQUA / WATER / EAU, GLYCERIN, ALCOHOL DENAT., PROPYLENE GLYCOL, PANTHENOL, PENTYLENE GLYCOL, DIMETHICONE, PEG-6 CAPRYLIC/CAPRIC GLYCERIDES, ALPINIA GALANGA LEAF EXTRACT, CALCIUM CHLORIDE, GLYCERYL ISOSTEARATE, MADECASSOSIDE, PPG-6-DECYLTETRADECETH-30, SODIUM ACETYLATED HYALURONATE, SODIUM HYALURONATE, ALGIN, ADENOSINE, AMMONIUM POLYACRYLOYLDIMETHYL TAURATE, PROPANEDIOL, HYDROLYZED HYALURONIC ACID, HYDROXYACETOPHENONE, CAPRYLIC/CAPRIC TRIGLYCERIDE, CAPRYLYL GLYCOL, CITRIC ACID, TRISODIUM ETHYLENEDIAMINE DISUCCINATE, ACETYL GLUCOSAMINE, XANTHAN GUM, BUTYLENE GLYCOL, 1,2-HEXANEDIOL, TOCOPHEROL, PHENOXYETHANOL, PARFUM / FRAGRANCE'
PEEL = 'AQUA / WATER, ALCOHOL DENAT., LACTIC ACID, PROPANDIOL, MICA, GLYCOLIC ACID, CI77891 / TITANIUM DIOXIDE, GLUCONOLACTONE, GLYCERIN, SILICA, SODIUM HYDROXIDE, SALICYLIC ACID, NIACINAMIDE, SODIUM PHOSPHATE, DISODIUM PHOSPHATE, HYDROXYETHYLCELLULOSE, TRISODIUM ETHYLENEDIAMINE DISUCCINATE, XANTHAN GUM, POLYACRYLATE CROSSPOLYMER-6, POLYSORBATE 60, CI 14700 / RED 4, PARFUM / FRAGRANCE.'
RETINOL = 'AQUA / WATER , GLYCERIN , CYCLOHEXASILOXANE , ALCOHOL DENAT , PENTYLENE GLYCOL , NIACINAMIDE , DIMETHICONE , GLYCINE SOJA OIL / SOYBEAN OIL , PPG-6-DECYLTETRADECETH-30 , SODIUM HYALURONATE RETINOL , ADENOSINE , AMMONIUM POLYACRYLOYLDIMETHYL , TAURATE , CAPRYLYL GLYCOL , CITRIC ACID , TRISODIUM ETHYLENEDIAMINE DISUCCINATE , XANTHAN GUM , POLYS ILICONE-11 , RETINYL PALMITATE TOCOPHEROL , PHENOXYETHANOL , PARFUM / FRAGRANCE.'


NIGHT = 'AQUA / WATER, GLYCERIN, ISOPROPYL PALMITATE, ALCOHOL DENAT., NIACINAMIDE, BUTYROSPERMUM PARKII BUTTER / SHEA BUTTER, AMMONIUMPOLYACRYLOYLDIMETHYL TAURATE, LINALOOL, SODIUM HYDROXIDE, SODIUM POLYACRYLATE, SODIUM ACETYLATED HYALURONATE, SODIUMDEHYDROACETATE, SODIUM HYALURONATE, 2-OLEAMIDO-1,3OCTADECANEDIOL, PHENOXYETHANOL, LIMONENE, CAPRYLYL GLYCOL, TETRASODIUM GLUTAMATE DIACETATE, HYDROLYZED SOY PROTEIN, CITRONELLOL, CITRIC ACID, PHYTIC ACID, PANTHENOL, PENTYLENE GLYCOL, POLYEPSILON LYSINE, BENZYL ALCOHOL, CI 60730 / EXT.VIOLET 2, PARFUM / FRAGRANCE.'
VINYL = 'ISODODECANE, DIMETHICONE, TRIMETHYLSILOXYSILICATE, POLYMETHYLSILSESQUIOXANE/ TRIMETHYLSILOXYSILICATE, POLYPROPYLSILSESQUIOXANE, C30-45 ALKYLDIMETHYLSILYL POLYPROPYLSILSESQUIOXANE, TRIMETHYLSILOXYPHENYL DIMETHICONE, TRIMETHYL PENTAPHENYL TRISILOXANE, BIS-STEARYL DIMETHICONE, DIMETHICONOL, TRIHYDROXYSTEARIN, PHENOXYETHANOL, ALUMINA, ETHYLHEXYLGLYCERIN, TOCOPHERYL ACETATE, TRIETHOXYCAPRYLYLSILANE'
GOLD = 'ISODODECANE, CAPRYLIC/CAPRIC TRIGLYCERIDE, DIMETHICONE, DICAPRYLYL ETHER, DIMETHICONOL, TRIMETHYLSILOXYSILICATE, CHAMOMILLA RECUTITA FLOWER EXTRACT / MATRICARIA FLOWER EXTRACT, COCOS NUCIFERA OIL / COCONUT OIL, TOCOPHEROL, ETHYLHEXYL SALICYLATE, HELIANTHUS ANNUUS SEED OIL / SUNFLOWER SEED OIL, NELUMBO NUCIFERA FLOWER EXTRACT, LIMONENE, LINUM USITATISSIMUM FLOWER EXTRACT / LINSEED FLOWER EXTRACT, ISOEUGENOL, CAPRYLIC/CAPRIC GLYCERIDES, HIPPOPHAE RHAMNOIDES SEED OIL, PARFUM / FRAGRANCE, GARDENIA TAITENSIS FLOWER, FARNESOL, BISABOLOL, ROSA CANINA FLOWER EXTRACT, CITRAL, SQUALANE.'
SCALP = 'AQUA / WATER, ALCOHOL, DIAMINOPYRIMIDINE OXIDELACTIC ACID TOCOPHEROL, SODIUM HYALURONATE, SODIUM CITRATE, CAFFEINE, SAFFLOWER GLUCOSIDE, PEG-40 HYDROGENATED CASTOR OILARGININE, AMINOMETHYL PROPANOL, MENTHOL LINALOOL BENZYL SALICYLATE, BENZYL ALCOHOL, PARFUM / FRAGRANCE, ACRYLATES / BEHENETH-25 METHACRYLATE COPOLYMERPIROCTONE OLAMINECITRONELLOL, LAVANDULA HYBRIDA OIL, GLYCERIN'


def build():
    sources, products = {}, []

    def add(family, name, url, category, form, areas, claims, sizes=(None,),
            shades=(None,), finish=None, raw=None, key_ingredients=None, warning=None,
            variant=None, source_type='official_my_brand', partial=False, quarantine=False,
            ingredient_basis=None):
        source_id = family+'-my-pdp'
        sources[source_id] = {'url':url, 'source_type':source_type, 'verified_on':VERIFIED,
            'timestamp_precision':'day', 'access_method':'manual_public_page_or_indexed_extract',
            'scope':'MY product listing; availability and current package formula unverified'}
        for size in sizes:
            for shade in shades:
                suffix = (shade or size or 'unspecified').lower().replace(' ', '-')
                ingredients = ([normalize_ingredient(i.rstrip('.')) for i in re.split(r',\s+(?=\S)|,(?=[A-Z])',raw)]
                               if raw and not partial else key_ingredients)
                values = {'brand': 'Maybelline New York' if url.startswith(MAYBELLINE) else
                          'La Roche-Posay' if url.startswith(LRP) or source_type=='my_retailer' else "L'Oreal Paris",
                          'product_name':name, 'market':'MY', 'category':category,
                          'subcategory': {'hair_oil':'hair_treatment','scalp_essence':'scalp_treatment',
                                          'lip_tint':'lip_colour','liquid_lipstick':'lip_colour',
                                          'bullet_lipstick':'lip_colour','skin_tint':'foundation'}.get(form, form),
                          'product_format':form,'application_area':areas, 'finish':finish,
                          'raw_ingredients':raw, 'normalized_ingredients':ingredients,
                          'variant':variant,'shade':shade,'size':size,'occasions':None,
                          'manufacturer_claims':[{'concept':c,'text':text,
                              'claim_type':'retailer_reported_brand_claim' if source_type=='my_retailer' else 'manufacturer_claim',
                              'independently_verified':False} for c,text in claims] or None}
                quality = {}
                for field in FIELDS:
                    value = values[field]
                    state = 'unknown' if value is None else 'verified'
                    if field in ('raw_ingredients','normalized_ingredients') and (partial or not raw) and value is not None:
                        state = 'partial'
                    basis = {'manufacturer_claims':'Product details/benefits; concise paraphrase, not measured efficacy',
                             'application_area':'Usage/application section or explicit product application in title',
                             'raw_ingredients':'Ingredients section; punctuation retained except bullet delimiters normalized to commas',
                             'normalized_ingredients':ingredient_basis or 'Exact INCI tokens; explicit curated key ingredients if full list unavailable',
                             'size':'PDP size selector', 'shade':'PDP shade selector',
                             'market':'Malaysian brand/retailer domain (listing, not stock)',
                             'category':'Curated taxonomy from PDP product type',
                             'subcategory':'Curated taxonomy from PDP product type',
                             'product_format':'PDP product name/details', 'finish':'PDP description of finish',
                             'variant':'PDP product name/selector', 'brand':'PDP brand',
                             'product_name':'PDP displayed product heading'}.get(field, 'Not recorded')
                    quality[field] = {'state':state, 'reason':None if value is not None else 'Not verified in curated source extract',
                                      'evidence':[{'source_id':source_id,'basis':basis}] if value is not None else []}
                products.append({'product_id':family+'-'+suffix,'family_id':family,
                    **values, 'catalogue_version':VERSION,'source_id':source_id,
                    'verified_on':VERIFIED,'ingredient_completeness':'complete' if raw and not partial else 'partial' if ingredients else 'unknown',
                    'field_quality':quality, 'requires_review':quarantine,
                    'quality_warnings':[warning] if warning else []})

    add('lp-ha', 'Revitalift Hyaluronic Acid Serum (Plump, Youthful, Radiance, Hydration)',
        LOREAL+'revitalift/hyaluronic-acid/revitalift-hyaluronic-acid-serum-15ml',
        'skincare','serum',None,[('hydration','Brand declares hydration'),('radiance','Brand declares radiance')],
        sizes=('15ml','30ml'),raw=HA,warning='Application area not explicit in retained extract; do not infer it from category')
    add('lp-oil-control','Revitalift Hyaluronic Acid Oil Control Serum',
        LOREAL+'revitalift/revitalift-hyaluronic-acid-oil-control-serum',
        'skincare','serum',None,[('hydration','Brand declares hydration'),('oil_control','Brand declares oil control')], raw=OIL_CONTROL,
        warning='Size and explicit application area not verified; do not infer application from skincare category')
    add('lp-night','Revitalift Filler Line Plumping Water Night Cream',
        LOREAL+'revitalift/hyaluronic-acid/filler-line-plumping-water-night-cream',
        'skincare','cream',['face','neck'],[('hydration','Brand declares moisture retention')],sizes=('50ml',),
        raw=NIGHT)
    add('lp-aura-night','Aura Perfect Clinical Overnight Treatment',
        LOREAL+'aura-perfect/aura-perfect-clinical-overnight-treatment-50ml',
        'skincare','cream',['face','neck'],[('radiance','Brand declares improved radiance'),('even_tone','Brand declares more even tone')],
        sizes=('50ml',),key_ingredients=['niacinamide','sodium hyaluronate'],partial=True)
    add('lp-aura-day','Aura Perfect Clinical Day Cream SPF 19 PA+++',
        LOREAL+'aura-perfect/aura-perfect-clinical-day-cream-spf-19-pa',
        'skincare','cream',['face','neck'],[('hydration','Brand declares moisturization'),('even_tone','Brand declares more even tone')],
        sizes=('50ml',),key_ingredients=['niacinamide'],partial=True)
    add('lp-peel','Glycolic Bright Anti-Dark Spot Exfoliant Peel',
        LOREAL+'glycolic-bright/glycolic-bright-anti-dark-spot-exfoliant-peel',
        'skincare','peel',['face'],[('radiance','Brand declares radiance'),('soothing','Brand declares soothing')],sizes=('25ml',),raw=PEEL,
        warning='Rinse-off exfoliant peel; not treated as a leave-on serum despite marketing using both terms')
    add('lp-eye','Glycolic Bright 3% [GLYCOLIC + VIT CG + NIACINAMIDE] Dark Circle Eye Serum',
        LOREAL+'glycolic-bright/glycolic-bright-3-glycolic-acid-eye-serum-20ml',
        'skincare','serum',['eye_contour'],[('even_tone','Brand declares dark-circle appearance benefit')],
        sizes=('20ml',),key_ingredients=['niacinamide'],partial=True,ingredient_basis='Explicit ingredient complex in PDP heading')
    add('lrp-b5','HYALU B5 SURACTIVATED SERUM', LRP+'en-my/hyalu-b5/hyalu-b5-suractivated-serum',
        'skincare','serum',['face','neck','decollete'],[('barrier_repair','Brand declares skin barrier repair'),('hydration','Brand declares hydration'),('radiance','Brand declares glow')],
        sizes=('30ml','50ml'),raw=B5,warning='Source says alcohol free but INCI lists ALCOHOL DENAT.; conflicting alcohol claim excluded')
    add('lrp-mela','MELA B3 SERUM',LRP+'ms-my/mela-b3/mela-b3-serum',
        'skincare','serum',None,[('even_tone','Brand declares dark-spot appearance benefit')],sizes=('30ml',),
        key_ingredients=['niacinamide','retinyl palmitate'],partial=True,
        warning='Indexed MY source extract; application area not retained; retinyl palmitate is not retinol')
    add('lrp-retinol','Retinol B3 Serum Anti-Wrinkle 30ml',
        'https://www.watsons.com.my/la-roche-posay-retinol-b3-serum-anti-wrinkle-30ml/p/BP_80565',
        'skincare','serum',['face','neck'],[('radiance','Retailer reports luminous skin claim')], sizes=('30ml',),raw=RETINOL,
        key_ingredients=['retinol','niacinamide','retinyl palmitate'],partial=True,source_type='my_retailer',
        warning='Retailer INCI has missing delimiters; only explicitly named ingredients normalized',
        ingredient_basis='Retinol explicitly named in product heading/benefit text; niacinamide and retinyl palmitate in ingredient section')
    add('mb-teddy','SUPER STAY TEDDY TINT',MAYBELLINE+'lip-makeup/lipstick/superstay-teddy-tint',
        'makeup','lip_tint',['lips','cheeks'],[('long_wear','Brand declares long wear')],finish='matte',
        warning='Shade and size not verified; formula-level unspecified variant, not a purchasable SKU')
    add('mb-vinyl','SUPER STAY VINYL INK',MAYBELLINE+'lip-makeup/lipstick/super-stay-vinyl-ink-liquid-lipstick',
        'makeup','liquid_lipstick',['lips'],[('long_wear','Brand declares long wear'),('intense_colour','Brand declares high-impact colour')],
        shades=('10 LIPPY','15 PEACHY','20 COY','30 UNRIVALED','35 CHEEKY'),finish='vinyl_shine', raw=VINYL, partial=True,
        key_ingredients=['tocopheryl acetate'],
        warning='Shade selector verified from indexed MY PDP; no current stock or shade-specific INCI verified')
    add('mb-ultimatte','COLOR SENSATIONAL ULTIMATTE',MAYBELLINE+'lip-makeup/lipstick/color-sensational-ultimatte-lipstick',
        'makeup','bullet_lipstick',['lips'],[('intense_colour','Brand declares intense colour')],
        shades=('1099 MORE PEACH','1199 MORE ALMOND'),finish='matte')
    add('mb-fresh','FIT ME FRESH TINT',MAYBELLINE+'face-makeup/foundation/fit-me-fresh-tint',
        'makeup','skin_tint',['face'],[('radiance','Brand declares radiant appearance')],finish='radiant',
        warning='Shade and size unverified; face skin tint, not lip tint')
    add('lp-foundation','Infallible 32H Matte Cover Liquid Foundation',
        LOREAL+'infallible/infallible-32h-matte-cover-liquid-foundation-253',
        'makeup','foundation',['face'],[('long_wear','Brand declares long wear')],shades=('253',),finish='matte',
        key_ingredients=['niacinamide'],partial=True)
    add('lp-gold','Elseve Extraordinary Oil GOLD',
        LOREAL+'elseve/extraordinary-oil/elseve-extraordinary-oil-gold-100ml',
        'haircare','hair_oil',['hair_lengths','hair_ends'],[('shine','Brand declares shine'),('smoothing','Brand declares smoothing')],
        sizes=('100ml','30ml'),variant='Gold',raw=GOLD)
    add('lp-pink','Elseve Extraordinary Oil Pink',
        LOREAL+'elseve/extraordinary-oil/elseve-extraordinary-oil-pink-100ml',
        'haircare','hair_oil',['hair_lengths','hair_ends'],[('smoothing','Brand declares frizz control')],
        sizes=('100ml','30ml'),variant='Pink',quarantine=True,
        warning='Source identity/INCI consistency requires manual verification: hair oil heading with surfactant-rich ingredient block; excluded from matches')
    add('lp-brown','Elseve Extraordinary Oil Brown',
        LOREAL+'elseve/extraordinary-oil/elseve-extraordinary-oil-brown-100ml',
        'haircare','hair_oil',['hair_lengths','hair_ends'],[('shine','Brand declares shine')],sizes=('100ml',),variant='Brown')
    add('lp-rose','Elseve Extraordinary Floral Oil Rose',
        LOREAL+'elseve/extraordinary-oil/elseve-extraordinary-floral-oil-rose-100ml',
        'haircare','hair_oil',['hair_lengths','hair_ends'],[('shine','Brand declares shine')],sizes=('100ml',),variant='Rose')
    add('lp-conditioner','Elseve Extraordinary Oil Smooth Conditioner',
        LOREAL+'elseve/extraordinary-oil/extraordinary-oil-smooth-conditioner-440ml',
        'haircare','conditioner',['hair_lengths','hair_ends'],[('smoothing','Brand declares smoothing')],sizes=('440ml',),
        warning='Usage explicitly avoids scalp; oil in name does not make this a hair oil')
    add('lp-shampoo','Elseve Extraordinary Oil Smooth Shampoo',
        LOREAL+'elseve/extraordinary-oil/extraordinary-oil-smooth-shampoo-440ml',
        'haircare','shampoo',['hair_lengths'],[('smoothing','Brand declares smoothing')],sizes=('440ml',))
    add('lp-scalp','Elseve Full Resist Anti Hair Fall Scalp Essence',
        LOREAL+'elseve/full-resist/anti-hair-fall-scalp-essence',
        'haircare','scalp_essence',['scalp'],[('scalp_care','Brand positions essence as scalp care')],sizes=('90ml',),
        raw=SCALP,key_ingredients=['caffeine','arginine'],partial=True,
        warning='Malformed source INCI; full list not normalized; quantitative hair-growth claims not adopted')
    add('lp-full-resist','Elseve Full Resist Shampoo|Anti Hair Loss/Anti Dandruff/Hair Fall Control',
        LOREAL+'elseve/full-resist/elseve-full-resist-shampoo-440ml',
        'haircare','shampoo',['scalp'],[('scalp_cleansing','Brand declares scalp cleansing')],sizes=('440ml',),
        key_ingredients=['caffeine','arginine'],partial=True,
        warning='Generic ingredient tiles ignored; only product-specific ingredients retained')
    return {'catalogue_version':VERSION,'verified_on':VERIFIED,'sources':sources,'products':products}


if __name__ == '__main__':
    path = ROOT/'data/products/catalogue.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(build(),indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    print(path)
