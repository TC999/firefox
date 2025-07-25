/* -*- Mode: C++; tab-width: 2; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* vim: set ts=2 sts=2 et sw=2 tw=80: */
/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#include "UtilityMediaServiceParent.h"

#include "GeckoProfiler.h"
#include "nsDebugImpl.h"

#include "MediaCodecsSupport.h"
#include "mozilla/RemoteMediaManagerParent.h"

#if defined(XP_WIN) && defined(MOZ_SANDBOX)
#  include "WMF.h"
#  include "WMFDecoderModule.h"
#  include "WMFUtils.h"

#  include "mozilla/sandboxTarget.h"
#  include "mozilla/ipc/UtilityProcessImpl.h"
#endif  // defined(XP_WIN) && defined(MOZ_SANDBOX)

#ifdef MOZ_WIDGET_ANDROID
#  include "mozilla/StaticPrefs_media.h"
#  include "AndroidDecoderModule.h"
#endif

#include "mozilla/ipc/UtilityProcessChild.h"
#include "mozilla/RemoteDecodeUtils.h"

#ifdef MOZ_WMF_MEDIA_ENGINE
#  include "mozilla/gfx/DeviceManagerDx.h"
#  include "mozilla/gfx/gfxVars.h"
#  include "gfxConfig.h"
#endif

#ifdef MOZ_WMF_CDM
#  include "mozilla/MFCDMParent.h"
#  include "mozilla/PMFCDM.h"
#endif

namespace mozilla::ipc {

UtilityMediaServiceParent::UtilityMediaServiceParent(
    nsTArray<gfx::GfxVarUpdate>&& aUpdates)
    : mKind(GetCurrentSandboxingKind()),
      mUtilityMediaServiceParentStart(TimeStamp::Now()) {
#ifdef MOZ_WMF_MEDIA_ENGINE
  if (mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM) {
    nsDebugImpl::SetMultiprocessMode("MF Media Engine CDM");
    profiler_set_process_name(nsCString("MF Media Engine CDM"));
    gfx::gfxConfig::Init();
    gfx::gfxVars::Initialize();
    for (auto& update : aUpdates) {
      gfx::gfxVars::ApplyUpdate(update);
    }
    gfx::DeviceManagerDx::Init();
    return;
  }
#endif
  if (GetCurrentSandboxingKind() != SandboxingKind::GENERIC_UTILITY) {
    nsDebugImpl::SetMultiprocessMode("Utility AudioDecoder");
    profiler_set_process_name(nsCString("Utility AudioDecoder"));
  }
}

UtilityMediaServiceParent::~UtilityMediaServiceParent() {
#ifdef MOZ_WMF_MEDIA_ENGINE
  if (mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM) {
    gfx::gfxConfig::Shutdown();
    gfx::gfxVars::Shutdown();
    gfx::DeviceManagerDx::Shutdown();
  }
#endif
#ifdef MOZ_WMF_CDM
  if (mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM) {
    MFCDMParent::Shutdown();
  }
#endif
}

/* static */
void UtilityMediaServiceParent::GenericPreloadForSandbox() {
#if defined(MOZ_SANDBOX) && defined(XP_WIN)
  // Preload AV dlls so we can enable Binary Signature Policy
  // to restrict further dll loads.
  UtilityProcessImpl::LoadLibraryOrCrash(L"mozavcodec.dll");
  UtilityProcessImpl::LoadLibraryOrCrash(L"mozavutil.dll");
#endif  // defined(MOZ_SANDBOX) && defined(XP_WIN)
}

/* static */
void UtilityMediaServiceParent::WMFPreloadForSandbox() {
#if defined(MOZ_SANDBOX) && defined(XP_WIN)
  // mfplat.dll and mf.dll will be preloaded by
  // wmf::MediaFoundationInitializer::HasInitialized()

#  if defined(NS_FREE_PERMANENT_DATA)
  // WMF Shutdown requires this or it will badly crash
  UtilityProcessImpl::LoadLibraryOrCrash(L"ole32.dll");
#  endif  // defined(NS_FREE_PERMANENT_DATA)

  auto rv = wmf::MediaFoundationInitializer::HasInitialized();
  if (!rv) {
    NS_WARNING("Failed to init Media Foundation in the Utility process");
    return;
  }
#endif  // defined(MOZ_SANDBOX) && defined(XP_WIN)
}

void UtilityMediaServiceParent::Start(
    Endpoint<PUtilityMediaServiceParent>&& aEndpoint) {
  MOZ_ASSERT(NS_IsMainThread());

  DebugOnly<bool> ok = std::move(aEndpoint).Bind(this);
  MOZ_ASSERT(ok);

#ifdef MOZ_WIDGET_ANDROID
  if (StaticPrefs::media_utility_android_media_codec_enabled()) {
    AndroidDecoderModule::SetSupportedMimeTypes();
  }
#endif

  auto supported = media::MCSInfo::GetSupportFromFactory();
  Unused << SendUpdateMediaCodecsSupported(GetRemoteMediaInFromKind(mKind),
                                           supported);
  PROFILER_MARKER_UNTYPED("UtilityMediaServiceParent::Start", IPC,
                          MarkerOptions(MarkerTiming::IntervalUntilNowFrom(
                              mUtilityMediaServiceParentStart)));
}

mozilla::ipc::IPCResult
UtilityMediaServiceParent::RecvNewContentRemoteMediaManager(
    Endpoint<PRemoteMediaManagerParent>&& aEndpoint,
    const ContentParentId& aParentId) {
  MOZ_ASSERT(NS_IsMainThread());
  if (!RemoteMediaManagerParent::CreateForContent(std::move(aEndpoint),
                                                  aParentId)) {
    return IPC_FAIL_NO_REASON(this);
  }
  return IPC_OK();
}

#ifdef MOZ_WMF_MEDIA_ENGINE
mozilla::ipc::IPCResult UtilityMediaServiceParent::RecvInitVideoBridge(
    Endpoint<PVideoBridgeChild>&& aEndpoint,
    const ContentDeviceData& aContentDeviceData) {
  MOZ_ASSERT(mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM);
  if (!RemoteMediaManagerParent::CreateVideoBridgeToOtherProcess(
          std::move(aEndpoint))) {
    return IPC_FAIL_NO_REASON(this);
  }

  gfx::gfxConfig::Inherit(
      {
          gfx::Feature::HW_COMPOSITING,
          gfx::Feature::D3D11_COMPOSITING,
          gfx::Feature::OPENGL_COMPOSITING,
          gfx::Feature::DIRECT2D,
      },
      aContentDeviceData.prefs());

  if (gfx::gfxConfig::IsEnabled(gfx::Feature::D3D11_COMPOSITING)) {
    if (auto* devmgr = gfx::DeviceManagerDx::Get()) {
      devmgr->ImportDeviceInfo(aContentDeviceData.d3d11());
    }
  }

  Unused << SendCompleteCreatedVideoBridge();
  return IPC_OK();
}

IPCResult UtilityMediaServiceParent::RecvUpdateVar(
    const GfxVarUpdate& aUpdate) {
  MOZ_ASSERT(mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM);
  auto scopeExit = MakeScopeExit(
      [self = RefPtr<UtilityMediaServiceParent>{this},
       location = GetRemoteMediaInFromKind(mKind),
       couldUseHWDecoder = gfx::gfxVars::CanUseHardwareVideoDecoding()] {
        if (couldUseHWDecoder != gfx::gfxVars::CanUseHardwareVideoDecoding()) {
          // The capabilities of the system may have changed, force a refresh by
          // re-initializing the PDM.
          Unused << self->SendUpdateMediaCodecsSupported(
              location,
              media::MCSInfo::GetSupportFromFactory(true /* force refresh */));
        }
      });
  gfx::gfxVars::ApplyUpdate(aUpdate);
  return IPC_OK();
}
#endif

#ifdef MOZ_WMF_CDM
IPCResult UtilityMediaServiceParent::RecvGetKeySystemCapabilities(
    GetKeySystemCapabilitiesResolver&& aResolver) {
  MOZ_ASSERT(mKind == SandboxingKind::MF_MEDIA_ENGINE_CDM);
  MFCDMParent::GetAllKeySystemsCapabilities()->Then(
      GetCurrentSerialEventTarget(), __func__,
      [aResolver](CopyableTArray<MFCDMCapabilitiesIPDL>&& aCapabilities) {
        aResolver(std::move(aCapabilities));
      },
      [aResolver](nsresult) {
        aResolver(CopyableTArray<MFCDMCapabilitiesIPDL>());
      });
  return IPC_OK();
}

IPCResult UtilityMediaServiceParent::RecvUpdateWidevineL1Path(
    const nsString& aPath) {
  MFCDMParent::SetWidevineL1Path(NS_ConvertUTF16toUTF8(aPath).get());
  return IPC_OK();
}
#endif

}  // namespace mozilla::ipc
