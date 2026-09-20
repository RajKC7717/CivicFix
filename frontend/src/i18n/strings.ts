/**
 * UI strings in English, Hindi and Marathi.
 *
 * A hand-written dictionary rather than a library: the string set is small, the
 * bundle stays tiny, and there is no runtime loader that can fail on a venue
 * network. `Dict` is derived from the English object, so TypeScript refuses to
 * compile if a translation goes missing.
 *
 * Marathi is listed first in the switcher because this is Pune.
 */

export const en = {
  // --- shell ---
  appName: 'NagarNetra',
  tagline: 'The city, seen clearly',
  challenge: 'PS-18 CivicFix',
  nav_report: 'Report an issue',
  nav_track: 'Track a complaint',
  nav_map: 'City map',
  nav_officer: 'Officer login',
  language: 'Language',
  scope_notice:
    'Decision-support tool for municipal staff. Not an autonomous enforcement system. Final decisions rest with officers.',

  // --- home ---
  home_title: 'Report a civic problem in your own language',
  home_subtitle:
    'Type, speak or photograph the problem. NagarNetra understands Marathi, Hindi and English, finds everyone else who reported the same thing, and tells you exactly what happens next.',
  home_cta: 'Report an issue',
  home_track_cta: 'Track my complaint',
  home_stat_issues: 'Issues tracked',
  home_stat_resolved: 'Resolved',
  home_stat_citizens: 'Citizens reporting',
  home_stat_median: 'Median fix time',
  home_how_title: 'How it works',
  home_how_1_title: 'Say it your way',
  home_how_1_body:
    'Marathi, Hindi, English or a mix. Speak it if typing is hard. Add a photo if you have one.',
  home_how_2_title: 'We group the voices',
  home_how_2_body:
    'If your neighbours already reported the same pothole, your report joins theirs and pushes it up the queue instead of becoming a duplicate ticket.',
  home_how_3_title: 'You can follow it',
  home_how_3_body:
    'Every complaint gets a ticket number, a public timeline and a deadline. You can see why it was ranked the way it was.',
  home_recent: 'Open issues near you',

  // --- report form ---
  report_title: 'Report an issue',
  report_step_describe: 'Describe',
  report_step_locate: 'Locate',
  report_step_review: 'Send',
  report_what: 'What is the problem?',
  report_what_placeholder:
    'For example: there is a large pothole opposite Katraj dairy, near the school',
  report_what_hint:
    'Write in Marathi, Hindi or English, whichever is easiest. You can mix languages.',
  report_voice_start: 'Speak instead',
  report_voice_stop: 'Stop recording',
  report_voice_listening: 'Listening...',
  report_voice_unsupported:
    'Voice input is not available in this browser. Please type instead - it works exactly the same.',
  report_voice_error: 'Could not hear that. Please try again or type the complaint.',
  report_photo: 'Add a photo (optional)',
  report_photo_hint:
    'Photo metadata is removed before storage. Location is read from it only if you tick the box below.',
  report_photo_change: 'Change photo',
  report_photo_remove: 'Remove',
  report_exif_consent: 'Use the location stored in this photo',
  report_where: 'Where is it?',
  report_gps: 'Use my current location',
  report_gps_working: 'Finding you...',
  report_gps_done: 'Location captured',
  report_gps_denied:
    'Location permission was refused. Drop a pin on the map or describe the place below.',
  report_pin_hint: 'Tap the map to drop a pin',
  report_landmark: 'Or describe the place',
  report_landmark_placeholder: 'near Katraj dairy, opposite the petrol pump',
  report_landmark_hint:
    'A landmark is enough. We will place it on the map and an officer will confirm.',
  report_submit: 'Send complaint',
  report_sending: 'Sending...',
  report_privacy_note:
    'Phone numbers, e-mail addresses and ID numbers are removed automatically before your complaint is processed.',
  report_need_text: 'Please describe the problem, or attach a photo.',

  // --- ticket / result ---
  ticket_title: 'Complaint registered',
  ticket_number: 'Your ticket number',
  ticket_copy: 'Copy',
  ticket_copied: 'Copied',
  ticket_understood: 'What we understood',
  ticket_category: 'Category',
  ticket_severity: 'Severity',
  ticket_confidence: 'Confidence',
  ticket_decided_by: 'Decided by',
  ticket_why: 'Why this category',
  ticket_joined_title: 'You are not alone',
  ticket_priority: 'Priority',
  ticket_priority_why: 'Why this priority',
  ticket_deadline: 'Target resolution',
  ticket_department: 'Assigned to',
  ticket_track_cta: 'Track this complaint',
  ticket_new_cta: 'Report another issue',
  ticket_redacted: 'Removed for your privacy',
  ticket_review_note:
    'A municipal officer will review this personally. Your complaint has not been rejected.',

  // --- tracking ---
  track_title: 'Track a complaint',
  track_placeholder: 'Enter your ticket number, e.g. NN-7K3M92QP',
  track_button: 'Track',
  track_not_found: 'We could not find that ticket number. Please check and try again.',
  track_timeline: 'Progress',
  track_reported: 'Reported',
  track_others: 'people reported this issue',
  track_rate_title: 'Was it fixed properly?',
  track_rate_hint: 'Your rating is shown to the department and to the ward officer.',
  track_rate_comment: 'Anything to add? (optional)',
  track_rate_submit: 'Send rating',
  track_rate_thanks: 'Thank you - your rating helps hold the department to account.',
  track_rated: 'You rated this fix',

  // --- statuses ---
  status_received: 'Received',
  status_verified: 'Verified',
  status_assigned: 'Assigned',
  status_in_progress: 'In progress',
  status_resolved: 'Resolved',

  // --- generic ---
  loading: 'Loading...',
  retry: 'Try again',
  error_generic: 'Something went wrong. Your data is safe.',
  back: 'Back',
  next: 'Next',
  close: 'Close',
  cancel: 'Cancel',
  optional: 'optional',
  reports_one: 'report',
  reports_many: 'reports',
}

export type Dict = typeof en

export const hi: Dict = {
  appName: 'नगरनेत्र',
  tagline: 'शहर, साफ़ नज़र में',
  challenge: 'PS-18 CivicFix',
  nav_report: 'शिकायत दर्ज करें',
  nav_track: 'शिकायत देखें',
  nav_map: 'शहर का नक्शा',
  nav_officer: 'अधिकारी लॉगिन',
  language: 'भाषा',
  scope_notice:
    'यह नगर निगम कर्मचारियों के लिए एक सहायक उपकरण है, स्वचालित कार्रवाई प्रणाली नहीं। अंतिम निर्णय अधिकारी ही लेते हैं।',

  home_title: 'अपनी भाषा में नागरिक समस्या दर्ज करें',
  home_subtitle:
    'लिखिए, बोलिए या फ़ोटो भेजिए। नगरनेत्र मराठी, हिन्दी और अंग्रेज़ी समझता है, वही समस्या दर्ज करने वाले बाकी लोगों को जोड़ता है, और आगे क्या होगा यह साफ़ बताता है।',
  home_cta: 'शिकायत दर्ज करें',
  home_track_cta: 'मेरी शिकायत देखें',
  home_stat_issues: 'दर्ज समस्याएँ',
  home_stat_resolved: 'हल हुईं',
  home_stat_citizens: 'नागरिक',
  home_stat_median: 'औसत समाधान समय',
  home_how_title: 'यह कैसे काम करता है',
  home_how_1_title: 'अपने तरीके से कहिए',
  home_how_1_body:
    'मराठी, हिन्दी, अंग्रेज़ी या मिलाजुला। लिखना मुश्किल हो तो बोलिए। फ़ोटो हो तो जोड़िए।',
  home_how_2_title: 'हम आवाज़ें जोड़ते हैं',
  home_how_2_body:
    'अगर पड़ोसी वही गड्ढा पहले दर्ज कर चुके हैं, तो आपकी शिकायत उसी में जुड़ जाती है और प्राथमिकता बढ़ा देती है।',
  home_how_3_title: 'आप नज़र रख सकते हैं',
  home_how_3_body:
    'हर शिकायत को टिकट नंबर, सार्वजनिक टाइमलाइन और समय-सीमा मिलती है। प्राथमिकता क्यों मिली, यह भी दिखता है।',
  home_recent: 'आपके आसपास खुली समस्याएँ',

  report_title: 'शिकायत दर्ज करें',
  report_step_describe: 'समस्या',
  report_step_locate: 'स्थान',
  report_step_review: 'भेजें',
  report_what: 'समस्या क्या है?',
  report_what_placeholder: 'जैसे: कात्रज डेअरी के सामने बड़ा गड्ढा है, स्कूल के पास',
  report_what_hint: 'मराठी, हिन्दी या अंग्रेज़ी—जो आसान हो। भाषाएँ मिला भी सकते हैं।',
  report_voice_start: 'बोलकर बताइए',
  report_voice_stop: 'रिकॉर्डिंग रोकें',
  report_voice_listening: 'सुन रहे हैं...',
  report_voice_unsupported:
    'इस ब्राउज़र में आवाज़ सुविधा नहीं है। कृपया लिखकर भेजें—नतीजा वही रहेगा।',
  report_voice_error: 'सुनाई नहीं दिया। दोबारा कोशिश करें या लिखकर भेजें।',
  report_photo: 'फ़ोटो जोड़ें (वैकल्पिक)',
  report_photo_hint:
    'फ़ोटो का मेटाडेटा सहेजने से पहले हटा दिया जाता है। स्थान तभी पढ़ा जाता है जब आप नीचे अनुमति दें।',
  report_photo_change: 'फ़ोटो बदलें',
  report_photo_remove: 'हटाएँ',
  report_exif_consent: 'इस फ़ोटो में सहेजा गया स्थान उपयोग करें',
  report_where: 'यह कहाँ है?',
  report_gps: 'मेरा वर्तमान स्थान लें',
  report_gps_working: 'स्थान खोज रहे हैं...',
  report_gps_done: 'स्थान मिल गया',
  report_gps_denied: 'स्थान की अनुमति नहीं मिली। नक्शे पर पिन लगाएँ या जगह बताएँ।',
  report_pin_hint: 'पिन लगाने के लिए नक्शे पर टैप करें',
  report_landmark: 'या जगह बताइए',
  report_landmark_placeholder: 'कात्रज डेअरी के पास, पेट्रोल पंप के सामने',
  report_landmark_hint:
    'कोई निशानी बताना काफ़ी है। हम नक्शे पर रखेंगे और अधिकारी पुष्टि करेंगे।',
  report_submit: 'शिकायत भेजें',
  report_sending: 'भेजा जा रहा है...',
  report_privacy_note:
    'फ़ोन नंबर, ई-मेल और पहचान संख्याएँ प्रोसेस करने से पहले अपने आप हटा दी जाती हैं।',
  report_need_text: 'कृपया समस्या बताइए, या फ़ोटो जोड़िए।',

  ticket_title: 'शिकायत दर्ज हो गई',
  ticket_number: 'आपका टिकट नंबर',
  ticket_copy: 'कॉपी',
  ticket_copied: 'कॉपी हो गया',
  ticket_understood: 'हमने क्या समझा',
  ticket_category: 'श्रेणी',
  ticket_severity: 'गंभीरता',
  ticket_confidence: 'विश्वास',
  ticket_decided_by: 'किसने तय किया',
  ticket_why: 'यह श्रेणी क्यों',
  ticket_joined_title: 'आप अकेले नहीं हैं',
  ticket_priority: 'प्राथमिकता',
  ticket_priority_why: 'यह प्राथमिकता क्यों',
  ticket_deadline: 'लक्षित समाधान',
  ticket_department: 'विभाग',
  ticket_track_cta: 'इस शिकायत पर नज़र रखें',
  ticket_new_cta: 'दूसरी शिकायत दर्ज करें',
  ticket_redacted: 'आपकी निजता के लिए हटाया गया',
  ticket_review_note:
    'एक नगर अधिकारी इसे स्वयं देखेंगे। आपकी शिकायत अस्वीकार नहीं हुई है।',

  track_title: 'शिकायत देखें',
  track_placeholder: 'अपना टिकट नंबर लिखें, जैसे NN-7K3M92QP',
  track_button: 'देखें',
  track_not_found: 'यह टिकट नंबर नहीं मिला। कृपया जाँचकर दोबारा कोशिश करें।',
  track_timeline: 'प्रगति',
  track_reported: 'दर्ज किया',
  track_others: 'लोगों ने यही समस्या दर्ज की',
  track_rate_title: 'क्या ठीक से काम हुआ?',
  track_rate_hint: 'आपकी रेटिंग विभाग और वार्ड अधिकारी को दिखती है।',
  track_rate_comment: 'कुछ और कहना है? (वैकल्पिक)',
  track_rate_submit: 'रेटिंग भेजें',
  track_rate_thanks: 'धन्यवाद — आपकी रेटिंग विभाग की जवाबदेही तय करने में मदद करती है।',
  track_rated: 'आपने इसे रेट किया',

  status_received: 'प्राप्त',
  status_verified: 'सत्यापित',
  status_assigned: 'सौंपा गया',
  status_in_progress: 'कार्य जारी',
  status_resolved: 'हल हुआ',

  loading: 'लोड हो रहा है...',
  retry: 'दोबारा कोशिश करें',
  error_generic: 'कुछ गड़बड़ हुई। आपका डेटा सुरक्षित है।',
  back: 'पीछे',
  next: 'आगे',
  close: 'बंद करें',
  cancel: 'रद्द करें',
  optional: 'वैकल्पिक',
  reports_one: 'शिकायत',
  reports_many: 'शिकायतें',
}

export const mr: Dict = {
  appName: 'नगरनेत्र',
  tagline: 'शहर, स्पष्ट दिसणारे',
  challenge: 'PS-18 CivicFix',
  nav_report: 'तक्रार नोंदवा',
  nav_track: 'तक्रार पाहा',
  nav_map: 'शहराचा नकाशा',
  nav_officer: 'अधिकारी लॉगिन',
  language: 'भाषा',
  scope_notice:
    'हे महापालिका कर्मचाऱ्यांसाठी निर्णय-सहाय्य साधन आहे, स्वयंचलित कारवाई प्रणाली नाही. अंतिम निर्णय अधिकारीच घेतात.',

  home_title: 'तुमच्या भाषेत नागरी समस्या नोंदवा',
  home_subtitle:
    'लिहा, बोला किंवा फोटो पाठवा. नगरनेत्र मराठी, हिन्दी आणि इंग्रजी समजते, तीच समस्या नोंदवणाऱ्या इतरांना जोडते, आणि पुढे काय होणार हे स्पष्ट सांगते.',
  home_cta: 'तक्रार नोंदवा',
  home_track_cta: 'माझी तक्रार पाहा',
  home_stat_issues: 'नोंदवलेल्या समस्या',
  home_stat_resolved: 'सोडवलेल्या',
  home_stat_citizens: 'नागरिक',
  home_stat_median: 'सरासरी सोडवण्याचा वेळ',
  home_how_title: 'हे कसे चालते',
  home_how_1_title: 'तुमच्या पद्धतीने सांगा',
  home_how_1_body:
    'मराठी, हिन्दी, इंग्रजी किंवा मिश्र. लिहिणे अवघड असेल तर बोला. फोटो असेल तर जोडा.',
  home_how_2_title: 'आम्ही आवाज एकत्र करतो',
  home_how_2_body:
    'शेजाऱ्यांनी तोच खड्डा आधीच नोंदवला असेल, तर तुमची तक्रार त्यातच जोडली जाते आणि प्राधान्य वाढवते.',
  home_how_3_title: 'तुम्ही पाठपुरावा करू शकता',
  home_how_3_body:
    'प्रत्येक तक्रारीला तिकीट क्रमांक, सार्वजनिक टाइमलाइन आणि मुदत मिळते. प्राधान्य का मिळाले हेही दिसते.',
  home_recent: 'तुमच्या परिसरातील खुल्या समस्या',

  report_title: 'तक्रार नोंदवा',
  report_step_describe: 'समस्या',
  report_step_locate: 'ठिकाण',
  report_step_review: 'पाठवा',
  report_what: 'समस्या काय आहे?',
  report_what_placeholder: 'उदा. कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ',
  report_what_hint: 'मराठी, हिन्दी किंवा इंग्रजी—जे सोपे वाटेल ते. भाषा मिसळल्या तरी चालेल.',
  report_voice_start: 'बोलून सांगा',
  report_voice_stop: 'रेकॉर्डिंग थांबवा',
  report_voice_listening: 'ऐकत आहोत...',
  report_voice_unsupported:
    'या ब्राउझरमध्ये आवाज सुविधा नाही. कृपया लिहून पाठवा—निकाल तोच राहील.',
  report_voice_error: 'ऐकू आले नाही. पुन्हा प्रयत्न करा किंवा लिहून पाठवा.',
  report_photo: 'फोटो जोडा (ऐच्छिक)',
  report_photo_hint:
    'फोटोचा मेटाडेटा साठवण्यापूर्वी काढून टाकला जातो. ठिकाण फक्त तुम्ही परवानगी दिल्यासच वाचले जाते.',
  report_photo_change: 'फोटो बदला',
  report_photo_remove: 'काढा',
  report_exif_consent: 'या फोटोमधील ठिकाण वापरा',
  report_where: 'हे कुठे आहे?',
  report_gps: 'माझे सध्याचे ठिकाण घ्या',
  report_gps_working: 'ठिकाण शोधत आहोत...',
  report_gps_done: 'ठिकाण मिळाले',
  report_gps_denied: 'ठिकाणाची परवानगी नाकारली. नकाशावर पिन लावा किंवा ठिकाण सांगा.',
  report_pin_hint: 'पिन लावण्यासाठी नकाशावर टॅप करा',
  report_landmark: 'किंवा ठिकाण सांगा',
  report_landmark_placeholder: 'कात्रज डेअरी जवळ, पेट्रोल पंपासमोर',
  report_landmark_hint:
    'एखादी खूण सांगितली तरी पुरेसे आहे. आम्ही ती नकाशावर ठेवू आणि अधिकारी खात्री करतील.',
  report_submit: 'तक्रार पाठवा',
  report_sending: 'पाठवत आहोत...',
  report_privacy_note:
    'फोन क्रमांक, ई-मेल आणि ओळख क्रमांक प्रक्रिया करण्यापूर्वी आपोआप काढले जातात.',
  report_need_text: 'कृपया समस्या सांगा, किंवा फोटो जोडा.',

  ticket_title: 'तक्रार नोंदवली गेली',
  ticket_number: 'तुमचा तिकीट क्रमांक',
  ticket_copy: 'कॉपी',
  ticket_copied: 'कॉपी झाले',
  ticket_understood: 'आम्हाला काय समजले',
  ticket_category: 'प्रकार',
  ticket_severity: 'तीव्रता',
  ticket_confidence: 'खात्री',
  ticket_decided_by: 'कोणी ठरवले',
  ticket_why: 'हा प्रकार का',
  ticket_joined_title: 'तुम्ही एकटे नाही',
  ticket_priority: 'प्राधान्य',
  ticket_priority_why: 'हे प्राधान्य का',
  ticket_deadline: 'अपेक्षित मुदत',
  ticket_department: 'विभाग',
  ticket_track_cta: 'या तक्रारीचा पाठपुरावा करा',
  ticket_new_cta: 'दुसरी तक्रार नोंदवा',
  ticket_redacted: 'तुमच्या गोपनीयतेसाठी काढले',
  ticket_review_note:
    'महापालिका अधिकारी हे स्वतः तपासतील. तुमची तक्रार नाकारलेली नाही.',

  track_title: 'तक्रार पाहा',
  track_placeholder: 'तुमचा तिकीट क्रमांक लिहा, उदा. NN-7K3M92QP',
  track_button: 'पाहा',
  track_not_found: 'हा तिकीट क्रमांक सापडला नाही. कृपया तपासून पुन्हा प्रयत्न करा.',
  track_timeline: 'प्रगती',
  track_reported: 'नोंदवले',
  track_others: 'लोकांनी हीच समस्या नोंदवली',
  track_rate_title: 'काम व्यवस्थित झाले का?',
  track_rate_hint: 'तुमचे रेटिंग विभागाला आणि प्रभाग अधिकाऱ्याला दिसते.',
  track_rate_comment: 'आणखी काही सांगायचे आहे? (ऐच्छिक)',
  track_rate_submit: 'रेटिंग पाठवा',
  track_rate_thanks: 'धन्यवाद — तुमचे रेटिंग विभागाची जबाबदारी निश्चित करण्यास मदत करते.',
  track_rated: 'तुम्ही याला रेटिंग दिले',

  status_received: 'प्राप्त',
  status_verified: 'पडताळले',
  status_assigned: 'नेमले',
  status_in_progress: 'काम सुरू',
  status_resolved: 'सोडवले',

  loading: 'लोड होत आहे...',
  retry: 'पुन्हा प्रयत्न करा',
  error_generic: 'काहीतरी चूक झाली. तुमचा डेटा सुरक्षित आहे.',
  back: 'मागे',
  next: 'पुढे',
  close: 'बंद करा',
  cancel: 'रद्द करा',
  optional: 'ऐच्छिक',
  reports_one: 'तक्रार',
  reports_many: 'तक्रारी',
}

export const DICTS = { en, hi, mr } as const
export type LangCode = keyof typeof DICTS

export const LANGUAGE_OPTIONS: { code: LangCode; label: string; native: string }[] = [
  { code: 'mr', label: 'Marathi', native: 'मराठी' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
  { code: 'en', label: 'English', native: 'English' },
]
