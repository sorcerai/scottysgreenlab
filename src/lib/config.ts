/**
 * Config loader — typed getters for template.config.ts
 *
 * Import this instead of template.config.ts directly.
 */

import config from '../../template.config';
import type { TemplateConfig } from '../../template.config';

export function getConfig(): TemplateConfig {
  return config;
}

export function getBrand() {
  return config.brand;
}

export function getAnalytics() {
  return config.analytics;
}

export function getSiteUrl(): string {
  return config.brand.url;
}

export function getPrimaryCta() {
  return config.content.primaryCta;
}

export function getBusinessType() {
  return config.businessType;
}

export function getOffices() {
  return config.offices;
}

export function getSocial() {
  return config.social;
}

export function getCrm() {
  return config.crm;
}

export function getTheme() {
  return config.theme;
}

export function getContentConfig() {
  return config.content;
}

export function getPseoConfig() {
  return config.pseo;
}

export function getBrainConfig() {
  return config.brain;
}

export function getComplianceNotes(): string[] {
  return config.content.complianceNotes;
}

export function getBrokerDisclaimer(): string | undefined {
  return config.content.brokerDisclaimer;
}
