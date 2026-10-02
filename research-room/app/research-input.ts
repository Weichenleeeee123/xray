export type ResearchInput = {
  company_name: string;
  need: string;
  scenario?: 'savings' | 'takeover' | 'job' | 'prepaid' | 'contract' | 'general' | null;
  for_whom?: string | null;
  amount?: number | null;
  material_text?: string | null;
  material_title?: string | null;
  refresh_sources?: boolean;
  [key: string]: unknown;
};

export type DemoCase = {
  id: string;
  label: string;
  real: boolean;
  ready: boolean;
  input: ResearchInput;
};

export function researchInput(company: string, need: string = '', preset?: ResearchInput): ResearchInput {
  const company_name = company.trim();
  const sameCompany = preset?.company_name.trim() === company_name;
  const sameNeed = sameCompany && preset?.need.trim() === need.trim();
  return {
    company_name,
    need: need.trim() || '了解这家公司的登记、资质与公开资料',
    ...(sameCompany ? { material_text: preset?.material_text, material_title: preset?.material_title } : {}),
    ...(sameCompany && typeof preset?.refresh_sources === 'boolean' ? { refresh_sources: preset.refresh_sources } : {}),
    ...(sameNeed ? { scenario: preset?.scenario, for_whom: preset?.for_whom, amount: preset?.amount } : {}),
  };
}
