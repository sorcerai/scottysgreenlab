/**
 * CRM provider abstraction — routes leads to the configured CRM.
 *
 * Providers:
 *   ghl      — GoHighLevel
 *   hubspot  — HubSpot
 *   webhook  — Generic webhook
 *   none     — Logs to console only
 */

import { getCrm } from '../config';

export interface LeadData {
  name: string;
  email: string;
  phone?: string;
  company?: string;
  source?: string;
  customFields?: Record<string, unknown>;
}

export interface LeadResult {
  success: boolean;
  id?: string;
  error?: string;
}

export interface CrmProvider {
  submitLead(data: LeadData): Promise<LeadResult>;
}

class GhlProvider implements CrmProvider {
  async submitLead(data: LeadData): Promise<LeadResult> {
    const apiKey = import.meta.env.GHL_API_KEY;
    const locationId = import.meta.env.GHL_LOCATION_ID;
    if (!apiKey || !locationId) {
      return { success: false, error: 'GHL_API_KEY and GHL_LOCATION_ID required' };
    }
    try {
      const response = await fetch('https://services.leadconnectorhq.com/contacts/', {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json', Version: '2021-07-28' },
        body: JSON.stringify({
          locationId, name: data.name, email: data.email,
          phone: data.phone || '', companyName: data.company || '',
          source: data.source || 'website',
          customFields: data.customFields ? Object.entries(data.customFields).map(([key, value]) => ({ id: key, field_value: value })) : [],
        }),
      });
      if (!response.ok) return { success: false, error: `GHL error (${response.status})` };
      const result = await response.json();
      return { success: true, id: result.contact?.id };
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Unknown GHL error' };
    }
  }
}

class HubSpotProvider implements CrmProvider {
  async submitLead(data: LeadData): Promise<LeadResult> {
    const apiKey = import.meta.env.HUBSPOT_API_KEY;
    if (!apiKey) return { success: false, error: 'HUBSPOT_API_KEY required' };
    try {
      const [firstName, ...rest] = data.name.split(' ');
      const properties: Record<string, string> = { firstname: firstName, lastname: rest.join(' ') || '', email: data.email };
      if (data.phone) properties.phone = data.phone;
      if (data.company) properties.company = data.company;
      const response = await fetch('https://api.hubapi.com/crm/v3/objects/contacts', {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ properties }),
      });
      if (!response.ok) return { success: false, error: `HubSpot error (${response.status})` };
      const result = await response.json();
      return { success: true, id: result.id };
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Unknown HubSpot error' };
    }
  }
}

class WebhookProvider implements CrmProvider {
  async submitLead(data: LeadData): Promise<LeadResult> {
    const webhookUrl = import.meta.env.WEBHOOK_URL;
    if (!webhookUrl) return { success: false, error: 'WEBHOOK_URL required' };
    try {
      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...data, submittedAt: new Date().toISOString() }),
      });
      if (!response.ok) return { success: false, error: `Webhook error (${response.status})` };
      try { const result = await response.json(); return { success: true, id: result.id }; } catch { return { success: true }; }
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Unknown webhook error' };
    }
  }
}

class NoneProvider implements CrmProvider {
  async submitLead(data: LeadData): Promise<LeadResult> {
    console.log('[CRM:none] Lead submitted (log only):', { name: data.name, email: data.email, timestamp: new Date().toISOString() });
    return { success: true, id: `local-${Date.now()}` };
  }
}

const providers: Record<string, () => CrmProvider> = {
  ghl: () => new GhlProvider(),
  hubspot: () => new HubSpotProvider(),
  webhook: () => new WebhookProvider(),
  none: () => new NoneProvider(),
};

export function getCrmProvider(): CrmProvider {
  const { provider } = getCrm();
  const factory = providers[provider];
  if (!factory) {
    console.warn(`[CRM] Unknown provider "${provider}", falling back to "none".`);
    return new NoneProvider();
  }
  return factory();
}
