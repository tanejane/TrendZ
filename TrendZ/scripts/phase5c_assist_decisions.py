"""Individually authored frozen-metadata review drafts, not matching rules or gold.

Anchors identify creators within the SHA-pinned snapshot, not list positions.
No draft here is an approved video-relevance judgment.
"""
SOURCE_SHA256 = '353594b06e4c8b709002231732bf0843f1e0d9e57d5560fe16eb83bb86b25205'

# anchor, label, domains, specializations, selected IDs, confidence, rationale
PROFILES = [
('YDFYDslevtE','supported','beauty fashion','makeup','YDFYDslevtE 26PRv7B0VeE D2wjdTo3i_U MsBg7kk1IbY xAfTSiLqeFw','high','Repeated makeup tests and outfit styling on separate dates; lip tint remains only one topic example.'),
('9anp6SS6-Lo','partially_supported','beauty lifestyle','haircare','vyePXB2sG8o fRg5aPfS0AI 9anp6SS6-Lo yW_z-mlD8Zc rHTZfigUCVQ','medium','Hair-product reviews recur within a mixed household-product sample spanning only nine days; specialization remains qualified.'),
('rA-x4pmXSrA','supported','beauty','skincare','rA-x4pmXSrA 6hc0kDETanQ 2_V7Tt364rg h5lWt2h1cKM FjfwJKHGKNs','high','Repeated ingredient, sunscreen and retinol skincare explanations across September and October.'),
('8y09OX4ZDrM','partially_supported','beauty','makeup','RROPjmjr1ig ph8xYVEV-sk 8y09OX4ZDrM jc6ng3ObJ1M','medium','Several explicit makeup tutorials on distinct dates, but the recent sample covers only six days and includes repeated promotion of look 03.'),
('yxzED0GgOic','supported','beauty health_wellness','haircare','yxzED0GgOic AZ8ugk8Q6Bw 08P1ALOs1bA cJJ8kAmQWzw','high','Repeated scalp assessment, hair restoration and hair-care content; medical credentials and treatment efficacy are not verified here.'),
('m63TmtjUumA','supported','lifestyle','','nlVxinRcPZc eOQvkU901sQ me4KRKyMMtw wShMKoq-RSQ','high','Repeated travel, food and leisure posts establish lifestyle content; one hair-oil review does not establish haircare specialization.'),
('c2ZDHBZz0po','supported','beauty','skincare makeup','c2ZDHBZz0po 6aPEzyTaJGc JQcPkfVykm4 CYuWUQR2qcg','high','Distinct serum/moisturizer reviews and blush/eye-makeup posts support both skincare and makeup.'),
('C_VwBaAj9Xk','partially_supported','beauty','skincare','C_VwBaAj9Xk EO-UzxbgxO8 JGr5x-C6J5I ZAkfszb-864','medium','Skincare posts recur, but the sample mixes older skincare with unrelated horror posts and near-identical recent glass-skin captions.'),
('JT9YP41LdEo','partially_supported','beauty','skincare makeup','JT9YP41LdEo yYs-X6NPhRA Q2SRwf5Ni8o 2EfNiAKuFqA','medium','Repeated skincare and makeup titles on distinct dates, but very compressed uploads and sparse descriptions limit profile depth.'),
('gm5t_i_pqUY','partially_supported','fashion beauty','makeup','qoPQfMZULnc J1zxMfM9yVU gm5t_i_pqUY Y7G9EAMM7WI','medium','Mostly repeated outfit posts, with two eye-makeup tutorials on different dates; broader makeup specialization needs inspection.'),
('zvUkec0MXi8','supported','beauty','skincare','hpcdwPqE-c0 Iy1v1_3QhYE G57WOf-Hcbc Qoo_QDHH2G0','high','Repeated skincare ingredients, routines and sunscreen topics; isolated hair-oil posts do not automatically expand specialization.'),
('F3FDhM230i8','supported','beauty','skincare','F3FDhM230i8 tuLeiwlz-K4 AFsGBmZ_vmo HfDVQIIVFsQ','high','Distinct skincare routine, skin-type and barrier education posts recur over multiple weeks.'),
('Ypj-r2kHKgA','partially_supported','beauty','skincare makeup','Ypj-r2kHKgA SaSw3bcw700 t72NW_r8diA JeIUgX45NrE','medium','Repeated skincare and lip-stain posts support a beauty profile; many hashtag-only entries leave substantive content unverified.'),
('sGSsauoqZpM','supported','beauty','skincare','sGSsauoqZpM zbv4pgNZ-Qw qupQjrkpptQ 1T0PckGk_JM','high','Repeated skincare education/product posts across several months; brand/product claims are not independently validated.'),
('5X7jmhKLjYU','partially_supported','beauty','haircare makeup','5X7jmhKLjYU AobNteZ2gHg nmW1PG0EeKY Yp8mZKF-6DQ x5x05mjAVdc','medium','Repeated hair-product and lip/blush captions, mainly short Portuguese promotional metadata; actual demonstrations need checking.'),
('oMHCYvoGMSY','supported','beauty','skincare haircare','oMHCYvoGMSY 2luFz9TIvbs 9AGPgsz3lMA EMCikRJtVYU','high','Repeated hair-oil and skincare-product postings on distinct dates; this is catalogue-style content, not independent product expertise.'),
('mV4-kihga8k','supported','beauty','skincare','mV4-kihga8k A_i-OAM1_XI beT5ScQbgfw Nv74Oc46AUA','high','Repeated substantive skincare routines and ingredient coverage; shampoo used for skin patches and lotion fragrance do not establish haircare/fragrance specializations.'),
('tSG0Thymbrw','supported','beauty health_wellness','skincare makeup','tSG0Thymbrw DGJcYMGNP6c BHPRzeqffds sbfULoq3u7A xHas5z9GZVY zyqY-zwC6Fc','high','Repeated skincare/makeup examples coexist with repeated fitness posts; fitness and popularity do not establish topic affinity.'),
('_H9Nng2knsQ','supported','beauty','skincare','_H9Nng2knsQ EMMMmhN_4bU nBJafqWMyew OfSbQc5jR5o','high','Repeated skincare ingredients, retinal/retinol comparisons and sunscreen content; retinoid terms remain distinct.'),
('hWyRJIzPPmw','partially_supported','beauty health_wellness','skincare','heOsNP4UTmA 8fLqiF3JSuc JRGI3cEgdOQ lNzyHEqEfdw','medium','Repeated skin-wellness and health content, but one Diwali makeup-preparation video and acne content do not establish repeated makeup practice.'),
('s9rvoInqcLM','partially_supported','beauty fashion','skincare makeup','s9rvoInqcLM Vl8WhPC7-IM VbfEENQH9mU -0oqPfyo9iI p_e1FoKfFAo 5mrhhIo2KqQ','medium','Skincare and makeup recur amid footwear/shopping posts; product-title captions alone provide qualified specialization evidence.'),
('aLjPW1sew3E','partially_supported','beauty lifestyle','makeup','h5gArUTkLQM yd0e29dQjHA aLjPW1sew3E -BtGekEC0lk tWd9LQBV9DY','low','Repeated brow/microblading procedures and travel are visible; lip coloring may be cosmetic tattooing rather than ordinary makeup, requiring manual classification.'),
('vXNFrqIcbNc','supported','beauty','makeup haircare','vXNFrqIcbNc WrTP2imVqoo pLEIcSbeWao coAJaX3lywg K1AV4XkKkKY','high','Explicit lip products/makeup and repeated heatless-curl hair tutorials on separate dates.'),
('DpG9AMj9-Ck','partially_supported','beauty','skincare','uzkYQ-oOltg S3EJRYVrzSc fVv824KQ2yY','low','Russian retinol and facial-serum wording repeats, often near-identically for one product; distinct uploads may be reposts rather than independent substantive examples.'),
('jtzl38VTvLA','partially_supported','lifestyle beauty','skincare','jtzl38VTvLA g3EGY-2pVy8 dtWqsQw1-3Y LYnK1ITvWdA','medium','Two explicit skincare posts months apart occur within mostly food/leisure content; specialization is qualified, not presumed from the seed.'),
('gJHRx2gcix8','partially_supported','lifestyle beauty','makeup','gJHRx2gcix8 _wziFEy-558 B5aeZ8uQVHE FLNpdi9qcaM','medium','Repeated travel/shopping content with two cosmetic finds; product discovery alone only weakly establishes makeup specialization.'),
('eq7RzqFKLQo','supported','beauty','skincare haircare','eq7RzqFKLQo UsU-6Uq8Bxc joJhS8kEA9s j-x1hLSTVGU 4eFxbjZc00U','high','Repeated skin-focused discussions plus two scalp/hair-serum videos; fragrance-avoidance ingredient discussions are not perfume specialization.'),
('vcMXtqVQYfk','supported','beauty','haircare makeup','MVg-5Qx5B-g P5T9e0CVW6k kerlrxctX34 3nVen7B62gk vYlhdI6bwZk','high','Repeated explicit Spanish hair-care tutorials and separate makeup/lip examples; hair serums must not be counted as skincare.'),
('ZO6-wvst2YM','partially_supported','beauty','skincare makeup','ZVIEqzExZok ECqsf054H1E 7wXgBS4oaBI XImrjnu1DoA ZO6-wvst2YM s433kR_D1PQ','medium','Repeated body-care and cosmetic swatch captions in Indonesian, but only a four-day sample with many product hashtags.'),
('mUP4IJNR1WQ','supported','beauty fashion lifestyle','makeup','mUP4IJNR1WQ PPRtiiTLTHE FV0XXLevolM HVXOk2Mr6jU x9NT6wWlqZA CDI_xzVRcFk czL4yHgiFqg','high','Makeup, outfits and home/leisure examples each recur on distinct dates; festive clothing is not itself Diwali makeup affinity.'),
('rGFmuEGoUpI','partially_supported','other','','SIyTGvmI7VM DzTSFDNfrJQ NitorqZmAg8','high','Sampled content is business/current-affairs reporting rather than beauty; all twenty uploads share one publication date, so do not validate a stable profile.'),
('0WiHtCkQ9cA','supported','beauty','haircare','0WiHtCkQ9cA lv-YqskLyRU mP-ENezt2UI hDWmh9Ex67A','medium','Repeated hair-cleansing/oiling content is explicit; sensational efficacy claims and possible repetitive formats are not verified.'),
('YNPokxU8d3w','supported','beauty health_wellness','skincare haircare','B2StdrxOzG4 TasNgyvQYzo YNPokxU8d3w NOENoWr9CAI jxgKHEBt4TI','high','Repeated skincare, haircare and health-condition discussions on separate dates despite the short sample window; professional credentials are not verified.'),
('kJnU0QmBosE','partially_supported','beauty','haircare','kJnU0QmBosE zLZJULNQJrA 0woClwz3Gd0 iT_8iPZjg9M','medium','Hair routines and tools recur across two dates, but most of the twenty rows are same-day shop posts; duplicate formats limit depth.'),
('XqrgQg-yGi8','supported','beauty lifestyle','skincare','XqrgQg-yGi8 Cr8eIsD54jo 543dqyaQ9Zg tLFodX66B_A -JUUsCw1hYs vYeflwYDVVE BCxh6BhdXpE','high','Repeated skincare tips/hauls and everyday-life posts; one barrier video remains separate from the broader profile.'),
('fKU8t3ACWx8','partially_supported','beauty','skincare','fKU8t3ACWx8 DQxa6LuhoVA','medium','Niacinamide and glycolic-acid/sunscreen posts on separate dates support a qualified skincare profile, but the sample is short and multilingual.'),
('qGAnRfvE6i4','insufficient_evidence','','','qGAnRfvE6i4','high','Only one sampled video exists; it cannot establish a stable creator domain or specialization.'),
('rBSOaRnFXIk','partially_supported','beauty','makeup','uZp8S84e9H4 qt8w_M2BNIE 60-7beW_4uc','medium','Makeup/hack titles recur on distinct dates, but only eight videos across three days support a qualified profile.'),
('vttx1g4GcWo','supported','beauty lifestyle','fragrance skincare','mp4oN29kXuI -TEWeID6L_0 8G_zWsem-o4 vttx1g4GcWo Sz15EJgJL5A GVFg1Yup8eU uvI-GSvLS6M','high','Perfume-layering and skincare routines recur separately, alongside home/leisure posts; no inference of retinol specialization from one routine.'),
('DHSSHeTky7E','supported','beauty','skincare makeup','DHSSHeTky7E 00yBkreAYKU emwY2hpIgoo nACTCAnchjc 4_kLHTFYRCc','high','Concrete serum/moisturizer and foundation/lip-product examples recur; generic makeup hashtags on skincare posts are excluded as support.'),
]

# anchor creator video, topic, draft label, explicitly selected IDs, confidence, reason,
# optional proxy/context IDs. These are individual judgments, not numeric strength gates.
AFFINITIES = [
('YDFYDslevtE','lip-tint','weak_affinity','YDFYDslevtE','high','One explicit tint test; other makeup/lipstick posts are not repeated tint evidence.'),
('9anp6SS6-Lo','hair-scalp-care','weak_affinity','9anp6SS6-Lo','high','One explicit scalp-treatment experience; other hair-product reviews do not establish repeated scalp coverage.'),
('rA-x4pmXSrA','retinol','strong_affinity','rA-x4pmXSrA i-kDV5HGR44 n3QNDcVTOJA 6hc0kDETanQ 2_V7Tt364rg BHqXRTDVrK8 nvSy7QFiTp4 h5lWt2h1cKM FjfwJKHGKNs','high','Multiple substantive retinol tutorials, use questions and product comparisons across September/October support a strong sampled draft; no new videos are human-approved.'),
('8y09OX4ZDrM','deepavali-glam','moderate_affinity','8y09OX4ZDrM jc6ng3ObJ1M','medium','Two dated makeup tutorials explicitly position the look for Diwali; separate look-03 promotional posts may duplicate the same content.','fadC8WLH0Gg'),
('yxzED0GgOic','hair-scalp-care','moderate_affinity','yxzED0GgOic AZ8ugk8Q6Bw 08P1ALOs1bA','medium','Scalp care, post-transplant scalp-care chapter and scalp examination recur; the scope is clinical scalp management, not automatically cosmetic routines.'),
('m63TmtjUumA','hair-oil','weak_affinity','m63TmtjUumA','high','One substantive hair-oil review in otherwise mixed lifestyle content.'),
('c2ZDHBZz0po','niacinamide','moderate_affinity','c2ZDHBZz0po _o9KxXZPf-4','medium','A serum review and a separate sunscreen caption name niacinamide on distinct dates; the latter is hashtag-only and needs content confirmation.'),
('C_VwBaAj9Xk','glass-skin','moderate_affinity','C_VwBaAj9Xk EO-UzxbgxO8 Z0-acS99WEU','medium','Explicit glass-skin posts recur, but two nearly identical recent captions and a much older post need duplicate/content inspection.'),
('JT9YP41LdEo','glass-skin','moderate_affinity','JT9YP41LdEo lilP5-68Nrw PSONjGxyvuk yYs-X6NPhRA vxGjFpfdQd4 EdTItu-AMgc','medium','Several explicit glass-skin routine titles across four dates; compressed repetitive uploads do not establish long-term sustained specialization.'),
('gm5t_i_pqUY','deepavali-glam','weak_affinity','gm5t_i_pqUY','high','Only the Diwali eye-makeup tutorial is explicit; festive outfits and generic glitter-eye makeup are not repeated Diwali evidence.'),
('zvUkec0MXi8','hair-oil','weak_affinity','xzaxtTHC3Qk','medium','French title describes an anti-traction-alopecia oil recipe; other oil/skin posts do not establish repeated explicit hair-oil coverage.'),
('zvUkec0MXi8','niacinamide','insufficient_evidence','','low','Niacinamide is a hashtag on a supplement-led caption; cosmetic topic coverage and substantive ingredient discussion are not established.','zvUkec0MXi8'),
('F3FDhM230i8','skin-barrier','moderate_affinity','F3FDhM230i8 7_581eK_ILI tuLeiwlz-K4','high','Damaged-barrier title and substantive seasonal-care/mistakes descriptions explicitly address barrier care on separate dates; repeated seasonal copy is not counted twice.'),
('Ypj-r2kHKgA','glass-skin','weak_affinity','th3feJl9yBA','medium','One inherited reviewed-relevant collagen-mask/glass-skin post; no repeated explicit coverage.'),
('Ypj-r2kHKgA','lip-tint','moderate_affinity','t72NW_r8diA JeIUgX45NrE','medium','Two lip-stain posts on separate dates; one is hashtag-only, so substantive repetition needs human confirmation.'),
('Ypj-r2kHKgA','niacinamide','weak_affinity','Ypj-r2kHKgA','medium','One niacinamide-serum hashtag title, supported by an inherited reviewed-relevant seed; no repeated ingredient coverage.'),
('Ypj-r2kHKgA','skin-barrier','weak_affinity','Xxj99kRNdoQ','medium','One cream description explicitly discusses supporting the skin barrier; generic skincare posts are not additional barrier evidence.'),
('sGSsauoqZpM','retinol','weak_affinity','FEml2eJ5xjk','medium','One eye-product description explicitly names retinol; no repeated substantive retinol coverage.'),
('sGSsauoqZpM','skin-barrier','weak_affinity','sGSsauoqZpM','high','One direct barrier-repair video; radiance/hydration posts alone are proxies, not repeated barrier content.'),
('5X7jmhKLjYU','hair-scalp-care','weak_affinity','5X7jmhKLjYU','medium','One inherited reviewed-relevant scalp-care coupon post; hair-balm and generic hair-care captions are not explicit scalp evidence.'),
('oMHCYvoGMSY','hair-oil','moderate_affinity','oMHCYvoGMSY 2luFz9TIvbs','medium','Two explicit hair-oil postings on different dates; short catalogue captions do not demonstrate depth or independent expertise.'),
('oMHCYvoGMSY','niacinamide','weak_affinity','Wk6APgnLmaY','high','One explicit niacinamide-product posting; no second substantive topic example.'),
('oMHCYvoGMSY','retinol','weak_affinity','9AGPgsz3lMA','high','One explicit retinol-serum posting; no repeated retinol history.'),
('mV4-kihga8k','niacinamide','moderate_affinity','NslTKtMMdi8 WWGUYVVsU8s','medium','A routine product list names niacinamide serum and a separate lotion post tags it; this is repeated mention, not ingredient expertise.'),
('mV4-kihga8k','retinol','insufficient_evidence','','low','Retinol occurs in a long remedies/ingredient list in a bleached-skin video; the metadata does not establish meaningful retinol coverage.','PrfK2TYV6Nk'),
('mV4-kihga8k','skin-barrier','moderate_affinity','mV4-kihga8k KKiDLtuuP3c','high','Direct damaged-barrier video and a separately timestamped barrier-repair chapter support repeated meaningful barrier coverage.'),
('tSG0Thymbrw','glass-skin','insufficient_evidence','','low','Glass-skin wording is confined to hashtags/search phrases on a barrier-cream review and a lip-combo post; glow/hydration is only proxy evidence.','tSG0Thymbrw BHPRzeqffds'),
('tSG0Thymbrw','lip-tint','weak_affinity','BHPRzeqffds','high','Products-used section explicitly identifies a lip tint in one lip-combo tutorial.'),
('tSG0Thymbrw','niacinamide','weak_affinity','tSG0Thymbrw','medium','One cream description names niacinamide as an ingredient; no repeated ingredient-focused evidence.'),
('tSG0Thymbrw','skin-barrier','moderate_affinity','tSG0Thymbrw DGJcYMGNP6c','medium','Two descriptions discuss restored moisture barrier and barrier protection; broader routine context limits depth.'),
('_H9Nng2knsQ','retinol','moderate_affinity','_H9Nng2knsQ P0e90bkrdBI OfSbQc5jR5o','medium','Explicit retinol comparison, usage-frequency discussion and retinol-cream review recur; retinal/tretinoin-only posts remain proxies.','EMMMmhN_4bU 1ehAhsgEmMs'),
('hWyRJIzPPmw','deepavali-glam','weak_affinity','hWyRJIzPPmw','high','One explicit Diwali makeup-preparation topic; other wellness content does not establish repeated festive-makeup coverage.'),
('hWyRJIzPPmw','hair-scalp-care','insufficient_evidence','','low','Scalp health is a passing reference in a general sleep description; hair-fall wellness content is only a proxy for scalp-care coverage.','JRGI3cEgdOQ R21sk5h8Sts'),
('hWyRJIzPPmw','skin-barrier','insufficient_evidence','','low','Only a skin-barrier hashtag appears in a menopause/pigmentation post; the description does not establish barrier-specific discussion.','8fLqiF3JSuc'),
('s9rvoInqcLM','lip-tint','insufficient_evidence','','low','A lip-balm product caption also tags lip tint; the metadata does not establish tint/stain format.','3MOOEEF3edg'),
('s9rvoInqcLM','niacinamide','weak_affinity','s9rvoInqcLM','high','One explicit niacinamide-serum post; no repeated ingredient history.'),
('aLjPW1sew3E','hair-scalp-care','weak_affinity','W8fRGi_HKBA','high','One explicit head-spa video from January 2025; other spa/travel posts do not establish repeated recent scalp coverage.'),
('aLjPW1sew3E','lip-tint','insufficient_evidence','','low','Lip tint/lip coloring occurs alongside microblading and tattoo-removal procedures; ordinary cosmetic lip tint versus permanent makeup is unresolved.','aLjPW1sew3E i4PZjzDP9Ys'),
('vXNFrqIcbNc','lip-tint','weak_affinity','vXNFrqIcbNc','high','One product-specific lip-stain demonstration; gloss and nude-lip captions are not additional verified stains.'),
('DpG9AMj9-Ck','retinol','insufficient_evidence','','low','Many Russian retinol captions repeat the same product and wording; distinct uploads/dates do not resolve whether the underlying content is repeated or substantive.','uzkYQ-oOltg S3EJRYVrzSc DpG9AMj9-Ck'),
('jtzl38VTvLA','retinol','weak_affinity','jtzl38VTvLA','high','One explicit collagen/retinol skincare routine; other skincare content is not repeated retinol evidence.'),
('gJHRx2gcix8','lip-tint','weak_affinity','gJHRx2gcix8','high','One explicit Teddy Tint product-find description in a travel-led sample.'),
('eq7RzqFKLQo','glass-skin','weak_affinity','eq7RzqFKLQo','high','One direct glass-skin discussion; other skincare topics are not automatically glass-skin coverage.'),
('eq7RzqFKLQo','niacinamide','moderate_affinity','joJhS8kEA9s oRXiqavmhkg X0tcQZW2lRU','medium','Multiple substantive ingredient/product discussions explicitly name niacinamide; do not infer dedicated ingredient specialization from passing product-list mentions.'),
('eq7RzqFKLQo','retinol','moderate_affinity','joJhS8kEA9s oRXiqavmhkg X0tcQZW2lRU','medium','Retinol is discussed in eye-cream, serum and Medicube comparisons on separate dates; tretinoin is not counted as retinol.'),
('eq7RzqFKLQo','skin-barrier','weak_affinity','eq7RzqFKLQo','high','One glass-skin description explicitly discusses barrier damage and repair; generic irritation discussion is not repeated barrier coverage.'),
('vcMXtqVQYfk','hair-oil','moderate_affinity','kerlrxctX34 vcMXtqVQYfk','medium','Spanish title explicitly compares hair oils, with a separate hair-product post tagged hair oil; serum-only and generic-routine hashtags remain unconfirmed.','f25jKqvsszg Tfq60jVkz6k iR27oCZII08'),
('ZO6-wvst2YM','lip-tint','weak_affinity','ZO6-wvst2YM','high','One explicit lip-tint swatch caption; other lip/makeup products are not necessarily tints.'),
('mUP4IJNR1WQ','deepavali-glam','weak_affinity','mUP4IJNR1WQ','high','One makeup look explicitly positioned for a Diwali party; generic festive makeup and festive clothing remain indirect.','FV0XXLevolM'),
('rGFmuEGoUpI','deepavali-glam','weak_affinity','emK1QNT5xkE','medium','One prior human-reviewed relevant seed lies outside the current all-news sample; title/description are absent, so fresh explanation verification is unavailable.'),
('0WiHtCkQ9cA','hair-oil','moderate_affinity','0WiHtCkQ9cA lv-YqskLyRU','medium','Two explicit oiling videos on separate dates; sensational efficacy claims and possible repeated formats require inspection, not validation.'),
('YNPokxU8d3w','hair-scalp-care','weak_affinity','YNPokxU8d3w','medium','Inherited reviewed-relevant seed discusses scalp traction within a broader hair routine; hair-growth-device content is proxy, not another approved scalp video.','NOENoWr9CAI'),
('YNPokxU8d3w','niacinamide','moderate_affinity','cowlrX49jHo TduTvjCQclc','medium','Separate review chapter and mask-ingredient discussion explicitly mention niacinamide; shopping lists alone are not dedicated coverage.'),
('YNPokxU8d3w','retinol','weak_affinity','heniIjy7aqA','medium','One shopping description explicitly lists a retinol product; AlphaRet/retinoid comparisons do not establish a second retinol-focused video.','xvM8ZhrSa7A uUTjhx278sw bjm7i9MSOfY'),
('YNPokxU8d3w','skin-barrier','weak_affinity','U0cXvfQ8h60','medium','One timestamped Q&A chapter directly addresses barrier support; an irritation caution and a cleanser hashtag are contextual, not repeated meaningful coverage.','AoBnmetAJkI QcpetfiTpqo'),
('kJnU0QmBosE','hair-scalp-care','weak_affinity','C1PambMnS9E','medium','Only the inherited reviewed-relevant seed establishes scalp relevance and lies outside the current sample; hair styling/shampoo shop posts are not additional explicit scalp evidence.'),
('XqrgQg-yGi8','skin-barrier','weak_affinity','XqrgQg-yGi8','medium','One inherited relevant barrier-repair caption; other general skincare posts do not establish repeated barrier history.'),
('fKU8t3ACWx8','niacinamide','weak_affinity','fKU8t3ACWx8','high','One explicit niacinamide-serum title; no second clear topic example.'),
('qGAnRfvE6i4','glass-skin','weak_affinity','qGAnRfvE6i4','high','One explicit glass-skin primer video; cannot support sustained affinity or a stable creator profile.'),
('rBSOaRnFXIk','glass-skin','weak_affinity','rBSOaRnFXIk','high','One explicit glass-skin glow post; other makeup looks are not repeated glass-skin evidence.'),
('vttx1g4GcWo','retinol','weak_affinity','vttx1g4GcWo','high','One routine description explicitly identifies retinol night cream; perfume/skincare profile does not imply repeated retinol affinity.'),
('DHSSHeTky7E','glass-skin','insufficient_evidence','','low','Glass-skin wording is a hashtag on a hydration/barrier routine; substantive explicit glass-skin content is not established.','-V58U3KmY0E'),
('DHSSHeTky7E','niacinamide','weak_affinity','DHSSHeTky7E','high','One description explicitly identifies The Ordinary niacinamide serum; other serums are not assumed to contain it.'),
('DHSSHeTky7E','skin-barrier','moderate_affinity','-V58U3KmY0E gIMKhB04p_Q','medium','Two descriptions explicitly position barrier-support routines/cream on separate dates; short promotional content limits depth.'),
]

# Judgments about the original frozen explanation, independent from proposed label.
PROFILE_EXCEPTIONS = {
 'mV4-kihga8k': ('unsupported', 'Haircare hits are skin-treatment shampoo references/general channel promotion; lotion fragrance is not repeated perfume content.'),
 'eq7RzqFKLQo': ('unsupported', 'Fragrance is discussed as an irritant in skincare, not as repeated perfume/fragrance-specialization content.'),
 'vcMXtqVQYfk': ('unsupported', 'Several proposed skincare examples are capillary/hair serums or concealer, not repeated skincare evidence.'),
 'hWyRJIzPPmw': ('unsupported', 'A single Diwali preparation title plus an acne post does not establish the proposed repeated makeup specialization.'),
}
AFFINITY_EXCEPTIONS = {
 ('tSG0Thymbrw','glass-skin'): ('unsupported', 'The two screened positives are hashtag/search-list hits; the lip-combo description does not substantiate glass-skin coverage.'),
 ('hWyRJIzPPmw','hair-scalp-care'): ('unsupported', 'A general sleep discussion passing reference is overstated as a relevant scalp-care video.'),
 ('hWyRJIzPPmw','skin-barrier'): ('unsupported', 'A hashtag does not substantiate the proposed relevant barrier-specific coverage.'),
 ('s9rvoInqcLM','lip-tint'): ('insufficient_evidence', 'Lip-balm/tint format is unresolved in the stored metadata.'),
 ('aLjPW1sew3E','lip-tint'): ('insufficient_evidence', 'The title alone does not resolve cosmetic lip tint versus a semi-permanent coloring procedure.'),
 ('DpG9AMj9-Ck','retinol'): ('insufficient_evidence', 'The screen misses Russian retinol wording beyond the seed; repost/content identity needs human inspection.'),
 ('DHSSHeTky7E','glass-skin'): ('unsupported', 'The explicit match is only a hashtag; the substantive routine description establishes hydration/barrier care, not explicit glass-skin coverage.'),
 ('rGFmuEGoUpI','deepavali-glam'): ('insufficient_evidence', 'Prior seed identity/provenance survives, but its title/description are missing from the fixed snapshot.'),
 ('kJnU0QmBosE','hair-scalp-care'): ('insufficient_evidence', 'Prior seed title/description are unavailable; new sampled content does not verify the old explanation.'),
 ('mV4-kihga8k','retinol'): ('insufficient_evidence', 'An isolated ingredient/remedies list is insufficient to verify substantive retinol coverage.'),
 ('zvUkec0MXi8','niacinamide'): ('insufficient_evidence', 'A supplement caption plus ingredient hashtag does not establish intended topical scope.'),
}


def author_decisions(records):
    profiles = [r['fixed'] for r in records if r['fixed']['unit_type'] == 'profile']
    anchors = {}
    for p in profiles:
        for v in p['videos']:
            if v['video_id'] in anchors:
                raise ValueError('Video anchor is not unique across creators')
            anchors[v['video_id']] = p
    fixed = {r['fixed']['unit_id']: r['fixed'] for r in records}
    output = []
    for anchor, label, domains, specs, ids, confidence, reason in PROFILES:
        unit = anchors[anchor]
        explanation, er = PROFILE_EXCEPTIONS.get(anchor, ('supported',
            'Stored example IDs/dates and qualified text-screen scope are traceable; broader identity/efficacy is not claimed.'))
        output.append({'unit_id': unit['unit_id'], 'proposed_label': label,
            'proposed_domains': domains.split(), 'proposed_specializations': specs.split(),
            'selected_video_ids': ids.split(), 'proxy_video_ids': [],
            'evidence_sufficiency': 'insufficient' if label == 'insufficient_evidence' else 'partial' if label == 'partially_supported' else 'sufficient',
            'explanation_support': explanation, 'explanation_reason': er,
            'reason': reason, 'confidence': confidence,
            'manual_question': reason if confidence != 'high' else ''})
    for raw in AFFINITIES:
        anchor, topic, label, ids, confidence, reason, *proxy = raw
        unit_id = 'affinity/' + anchors[anchor]['creator_id'] + '/' + topic
        if unit_id not in fixed:
            raise ValueError('Affinity is not a fixed review unit: ' + unit_id)
        explanation, er = AFFINITY_EXCEPTIONS.get((anchor, topic), ('supported',
            'Stored mentions and source/date references are traceable as provisional text screening, not validated affinity or product efficacy.'))
        output.append({'unit_id': unit_id, 'proposed_label': label,
            'selected_video_ids': ids.split(), 'proxy_video_ids': proxy[0].split() if proxy else [],
            'evidence_sufficiency': 'insufficient' if label == 'insufficient_evidence' else 'partial' if label == 'weak_affinity' else 'sufficient',
            'explanation_support': explanation, 'explanation_reason': er,
            'reason': reason, 'confidence': confidence,
            'manual_question': reason if confidence != 'high' else ''})
    return {'source_sha256': SOURCE_SHA256, 'review_basis': 'assisted_review', 'rows': output}
