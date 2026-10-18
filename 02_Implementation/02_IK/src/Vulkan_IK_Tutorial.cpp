#define GLFW_INCLUDE_VULKAN
#include <GLFW/glfw3.h>

#define GLM_FORCE_RADIANS
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>

#define GLM_ENABLE_EXPERIMENTAL
#include <glm/gtx/euler_angles.hpp>

#include <iostream>
#include <fstream>
#include <sstream>
#include <filesystem>
#include <cmath>
#include <string>
#include <stdexcept>
#include <algorithm>
#include <chrono>
#include <vector>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include <limits>
#include <array>
#include <optional>
#include <set>

const uint32_t WIDTH = 800;
const uint32_t HEIGHT = 600;

const int MAX_FRAMES_IN_FLIGHT = 2;

const std::vector<const char*> validationLayers = {
    "VK_LAYER_KHRONOS_validation"
};

const std::vector<const char*> deviceExtensions = {
    VK_KHR_SWAPCHAIN_EXTENSION_NAME
};

#ifdef NDEBUG
const bool enableValidationLayers = false;
#else
const bool enableValidationLayers = true;
#endif

VkResult CreateDebugUtilsMessengerEXT(VkInstance instance, const VkDebugUtilsMessengerCreateInfoEXT* pCreateInfo, const VkAllocationCallbacks* pAllocator, VkDebugUtilsMessengerEXT* pDebugMessenger) {
    auto func = (PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(instance, "vkCreateDebugUtilsMessengerEXT");
    if (func != nullptr) {
        return func(instance, pCreateInfo, pAllocator, pDebugMessenger);
    }
    else {
        return VK_ERROR_EXTENSION_NOT_PRESENT;
    }
}

void DestroyDebugUtilsMessengerEXT(VkInstance instance, VkDebugUtilsMessengerEXT debugMessenger, const VkAllocationCallbacks* pAllocator) {
    auto func = (PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(instance, "vkDestroyDebugUtilsMessengerEXT");
    if (func != nullptr) {
        func(instance, debugMessenger, pAllocator);
    }
}

struct QueueFamilyIndices {
    std::optional<uint32_t> graphicsFamily;
    std::optional<uint32_t> presentFamily;

    bool isComplete() {
        return graphicsFamily.has_value() && presentFamily.has_value();
    }
};

struct SwapChainSupportDetails {
    VkSurfaceCapabilitiesKHR capabilities;
    std::vector<VkSurfaceFormatKHR> formats;
    std::vector<VkPresentModeKHR> presentModes;
};

struct UniformBufferObject {
    alignas(16) glm::mat4 model;
    alignas(16) glm::mat4 view;
    alignas(16) glm::mat4 proj;
};

struct MeshPushConstants {
    float dt;
    float u_Time;
    uint32_t numWorkGroups;
    float youngsModulus;
    float poissonsRatio;
    uint32_t colorOffset;
	uint32_t colorCount;
};

struct Vertex {
    glm::vec3 pos;
    glm::vec3 color;
};

struct JointLimits {
    glm::vec2 flexionExtension; // x: Minimum Extension y: Maximum Flexion
    glm::vec2 abductionAdduction; // x: Minimum Adduction, y: Maximum Abduction
    glm::vec2 axialTwist; // x: Minimum Axial Twist, y: Maximum Axial Twist
};

struct Joint {
    glm::vec3 localPos;         // length of bone
	glm::vec3 pos; 		  // global position (computed from localPos and parent's transform)
    glm::vec3 angle;            // 
    JointLimits limits;
    glm::mat4 globalTransform;  // finally computed global transform
};

struct Finger {
    std::vector<Joint> joints;
	glm::vec3 rootOffset; // root joint position relative to the wrist
};

bool getValidLine(std::ifstream& file, std::string& line) {
    while (std::getline(file, line)) {
        if (line.empty()) continue;

        size_t first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        if (line[first] == '#') continue;

        return true;
    }

    return false;
}

struct NoteEvent {
    float time_ms;
    int pitch;
    int velocity;
    float duration_ms;
    int hand;
    int finger;
    // 손가락이 실제로 건반을 누르는 시간. 페달로 늘어난 소리 길이(duration_ms)와 달리
    // 손가락은 이 시점에 건반에서 떨어지므로, 눌림 판정은 반드시 이 값을 기준으로 한다.
    float key_hold_ms;
};

// 손가락 뼈대 전체 길이(1.0 + 0.5 + 0.25 = 1.75)에 맞춰 건반 폭을 잡아야 손과 비율이 맞음.
// getKeyLayout()과 initPianoKeyboard()가 반드시 이 값을 공유해야 건반 메시와 타겟 좌표가 어긋나지 않음.
const float kWhiteKeyWidth = 0.45f;

struct KeyLayout {
    bool isBlack;
    float z; // 건반의 중심 Z 위치 (getKeyPosition의 손끝 목표 Z와 동일한 좌표계)
};

KeyLayout getKeyLayout(int pitch) {
    // 옥타브 내 반음 인덱스(0=C, 1=C#, ... 11=B)와 옥타브 번호(Middle C=60 기준 0)
    int semitoneFromC4 = pitch - 60;
    int octave = (int)std::floor(semitoneFromC4 / 12.0f);
    int noteInOctave = semitoneFromC4 - octave * 12; // 0~11

    // 반음 인덱스별 흰 건반 여부
    static const bool isBlackKey[12] = { false, true, false, true, false, false, true, false, true, false, true, false };
    // 반음 인덱스가 속하는(또는 바로 왼쪽에 있는) 흰 건반의 옥타브 내 순서(0~6: C D E F G A B)
    static const float whiteKeyIndex[12] = { 0.0f, 0.0f, 1.0f, 1.0f, 2.0f, 3.0f, 3.0f, 4.0f, 4.0f, 5.0f, 5.0f, 6.0f };
    // 검은 건반이 인접한 두 흰 건반의 정중앙이 아니라 한쪽으로 치우쳐 있는 실제 피아노 형태 반영
    static const float blackKeyBias[12] = { 0.0f, -0.15f, 0.0f, 0.15f, 0.0f, 0.0f, -0.15f, 0.0f, 0.0f, 0.0f, 0.15f, 0.0f };

    // 한 옥타브에는 흰 건반이 7개뿐이므로, 반음 12개를 균등 배치하지 않고 흰 건반 폭 기준으로 배치
    float whiteKeyWidth = kWhiteKeyWidth;
    float octaveOffset = octave * 7.0f * whiteKeyWidth;
    float zPos = octaveOffset + whiteKeyIndex[noteInOctave] * whiteKeyWidth;

    bool isBlack = isBlackKey[noteInOctave];
    if (isBlack) {
        // 왼쪽 흰 건반과 다음 흰 건반 사이의 중간 지점에서 치우침(bias)만큼 이동
        zPos += whiteKeyWidth * (0.5f + blackKeyBias[noteInOctave]);
    }

    return { isBlack, zPos };
}

glm::vec3 getKeyPosition(int pitch) {
    KeyLayout layout = getKeyLayout(pitch);

    // 흰 건반은 손목 쪽 가까운 앞부분을 누르고, 검은 건반은 안쪽 깊숙히(손목에서 먼 쪽) 위치해 더 뻗어야 함
    // 검은 건반은 흰 건반보다 짧고 높게 솟아있어, 더 높은 위치(Y)에서 눌림
    float pressX = layout.isBlack ? 1.3f : 0.8f;
    float pressY = layout.isBlack ? -0.35f : -0.5f;

    return glm::vec3(pressX, pressY, layout.z);
}

// 전체 MIDI 노트 데이터를 담아둘 멤버 변수 (클래스 멤버로 선언)
std::vector<NoteEvent> parsedMidiData;

// 재생 루프 길이와 건반 표시 범위 (로드한 데이터에 맞춰 갱신됨)
float songLengthMs = 8000.0f;
int dataLowestPitch = 48;
int dataHighestPitch = 72;

// 01_Fingering 이 생성한 UE5 DataTable CSV (이 소스 파일 위치 기준 상대 경로)
const std::string kFingeringCsvPath =
    (std::filesystem::path(__FILE__).parent_path() /
     "../../01_Fingering/results/ue5/deb_clai_polyphonic_result_datatable.csv").lexically_normal().string();

// 로드한 노트들로 재생 길이와 음역을 계산
void updateSongInfo() {
    if (parsedMidiData.empty()) return;

    float endMs = 0.0f;
    int lo = 127, hi = 0;
    for (const auto& note : parsedMidiData) {
        endMs = std::max(endMs, note.time_ms + note.duration_ms);
        lo = std::min(lo, note.pitch);
        hi = std::max(hi, note.pitch);
    }
    songLengthMs = endMs + 500.0f; // 루프 직전에 손을 쉬는 여유

    // 88건반(A0~C8) 범위로 제한하고, 양 끝이 검은 건반이면 옆 흰 건반까지 넓혀 건반 모양을 마무리
    static const bool isBlackPc[12] = { false, true, false, true, false, false, true, false, true, false, true, false };
    lo = std::clamp(lo, 21, 108);
    hi = std::clamp(hi, 21, 108);
    if (isBlackPc[lo % 12]) lo--;
    if (isBlackPc[hi % 12]) hi++;
    dataLowestPitch = lo;
    dataHighestPitch = hi;
}

// 01_Fingering 의 UE5 DataTable CSV 를 읽어 parsedMidiData 를 채움
// 열 순서: Name,Pitch,StartMs,DurationMs,Hand,Role,Finger,Pressure,KeyDepth,IsBlack,WristPosNormalized,WristYawDeg,WristRollDeg,
//          KeyHoldMs,PedalDown,TargetXMm,TargetYMm,TargetZMm,BoneName,FrameIndex,ReleaseFrameIndex
bool loadFingeringCsv(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        std::cerr << "[Fingering] Failed to open CSV: " << path << std::endl;
        return false;
    }

    std::string line;
    if (!getValidLine(file, line)) return false; // 헤더 스킵

    std::vector<NoteEvent> notes;
    int skipped = 0;
    while (getValidLine(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();

        std::stringstream ss(line);
        std::vector<std::string> cols;
        std::string cell;
        while (std::getline(ss, cell, ',')) cols.push_back(cell);
        if (cols.size() < 14) { skipped++; continue; }

        try {
            NoteEvent note;
            note.pitch = std::stoi(cols[1]);
            note.time_ms = std::stof(cols[2]);
            note.duration_ms = std::stof(cols[3]);
            note.hand = (cols[4] == "Left") ? 0 : 1;
            note.finger = std::stoi(cols[6]);
            note.velocity = static_cast<int>(std::round(std::stof(cols[7]) * 127.0f));
            note.key_hold_ms = std::stof(cols[13]);

            // 6음 이상 화음에서 운지 엔진이 손가락을 배정하지 못한 음(finger=0)은 제외
            if (note.finger < 1 || note.finger > 5) { skipped++; continue; }
            notes.push_back(note);
        }
        catch (const std::exception&) {
            skipped++;
        }
    }

    if (notes.empty()) {
        std::cerr << "[Fingering] No valid notes in CSV: " << path << std::endl;
        return false;
    }

    std::sort(notes.begin(), notes.end(), [](const NoteEvent& a, const NoteEvent& b) { return a.time_ms < b.time_ms; });
    parsedMidiData = std::move(notes);
    updateSongInfo();

    std::cout << "[Fingering] " << parsedMidiData.size() << " notes loaded (skipped " << skipped << "), length "
              << songLengthMs / 1000.0f << "s, keys " << dataLowestPitch << "~" << dataHighestPitch << std::endl;
    return true;
}

// 가짜 MIDI 파싱 데이터를 생성하는 초기화 함수 (10손가락 양손 버전)
void initMockMidiData() {
    parsedMidiData.clear();

    // duration_ms를 450.0f로 주어, 음과 음 사이에 살짝 손을 떼는(50ms) 디테일을 추가했습니다.

    // =================================================================
    // [파트 1] 양손 반음계(크로매틱) 상행 - 흰/검은 건반 12개 모두 연주 (0.0초 ~ 5.95초, 원본과 동일한 500ms 간격)
    // =================================================================

    // 🖐️ 오른손: C4 ~ B4 반음계 12음 상행, 손가락은 1~5번을 순환 사용
    {
        for (int i = 0; i < 12; i++) {
            int pitch = 60 + i; // C4(60) ~ B4(71)
            int finger = (i % 5) + 1; // 1,2,3,4,5 순환
            parsedMidiData.push_back({ i * 500.0f, pitch, 80, 450.0f, 1, finger });
        }
    }

    // 🤚 왼손: C3 ~ B3 반음계 12음 상행, 손가락은 5~1번을 순환 사용
    // 주의: 피아노에서 왼손은 새끼손가락(5번)이 가장 낮은 음을 칩니다!
    {
        for (int i = 0; i < 12; i++) {
            int pitch = 48 + i; // C3(48) ~ B3(59)
            int finger = 5 - (i % 5); // 5,4,3,2,1 순환
            parsedMidiData.push_back({ i * 500.0f, pitch, 80, 450.0f, 0, finger });
        }
    }


    // =================================================================
    // [파트 2] 양손 웅장한 C Major 화음 동시 타건 (6.0초 ~ 7.5초, 파트 1이 끝난 뒤 시작)
    // =================================================================

    // 🤚 왼손 C3, E3, G3 (새끼, 중지, 엄지)
    parsedMidiData.push_back({ 6000.0f, 48, 90, 1500.0f, 0, 5 });
    parsedMidiData.push_back({ 6000.0f, 52, 90, 1500.0f, 0, 3 });
    parsedMidiData.push_back({ 6000.0f, 55, 90, 1500.0f, 0, 1 });

    // 🖐️ 오른손 C4, E4, G4 (엄지, 중지, 새끼)
    parsedMidiData.push_back({ 6000.0f, 60, 90, 1500.0f, 1, 1 });
    parsedMidiData.push_back({ 6000.0f, 64, 90, 1500.0f, 1, 3 });
    parsedMidiData.push_back({ 6000.0f, 67, 90, 1500.0f, 1, 5 });

    // 모의 데이터는 페달이 없으므로 누르는 시간 = 소리 길이
    for (auto& note : parsedMidiData) note.key_hold_ms = note.duration_ms;

    songLengthMs = 8000.0f;
    dataLowestPitch = 48;
    dataHighestPitch = 72;
}

// 운지 CSV 를 우선 로드하고, 실패하면 모의 데이터로 대체
void initNoteData() {
    if (!loadFingeringCsv(kFingeringCsvPath)) {
        std::cerr << "[Fingering] Falling back to mock MIDI data." << std::endl;
        initMockMidiData();
    }
}

// 2. 현재 시뮬레이션 시간에 맞춰 활성화된(눌려있는) 노트만 걸러내는 함수
std::vector<NoteEvent> getActiveNotesForCurrentTime(float currentTimeSec) {
    std::vector<NoteEvent> activeNotes;

    // 현재 시간을 밀리초(ms)로 변환 (곡 길이 단위로 반복)
    float currentTimeMs = std::fmod(currentTimeSec * 1000.0f, songLengthMs);

    for (const auto& note : parsedMidiData) {
        // 노트의 시작 시간 <= 현재 시간 < 건반 해제 시간(시작 + key_hold_ms)
        // 끝을 포함하면 같은 손가락의 앞 음 해제 시각 = 다음 음 시작 시각인 프레임에서 두 음이 동시에 눌린 것으로 판정됨
        if (currentTimeMs >= note.time_ms && currentTimeMs < (note.time_ms + note.key_hold_ms)) {
            activeNotes.push_back(note);
        }
    }

    return activeNotes;
}

class HelloTriangleApplication {
public:
    void run() {
        initWindow();
        //initFinger();
        initHand();
        initNoteData();
        initPianoKeyboard();
        initVulkan();
        mainLoop();
        cleanup();
    }

private:
    GLFWwindow* window;

    VkInstance instance;
    VkDebugUtilsMessengerEXT debugMessenger;
    VkSurfaceKHR surface;

    VkPhysicalDevice physicalDevice = VK_NULL_HANDLE;
    VkDevice device;

    VkQueue graphicsQueue;
    VkQueue presentQueue;

    VkSwapchainKHR swapChain;
    std::vector<VkImage> swapChainImages;
    VkFormat swapChainImageFormat;
    VkExtent2D swapChainExtent;
    std::vector<VkImageView> swapChainImageViews;
    std::vector<VkFramebuffer> swapChainFramebuffers;

    //depthImage, depthImageMemory;
    VkImage depthImage;
    VkDeviceMemory depthImageMemory;
    VkImageView depthImageView;

    VkRenderPass renderPass;

    VkDescriptorSetLayout descriptorSetLayout;
    VkPipelineLayout pipelineLayout;
    VkPipeline graphicsPipeline;
    VkPipeline pianoKeyPipeline;

    VkCommandPool commandPool;

    std::vector<Joint> joints;
	std::vector<Finger> hand;
    std::vector<Vertex> vertices;
    uint32_t pianoKeyVertexOffset = 0;
    uint32_t pianoKeyVertexCount = 0;

    // 카메라가 따라갈 두 손목의 중간 Z (updateJacobianKinematics 에서 갱신)
    float wristCenterZ = 0.0f;

    VkBuffer vertexBuffer;
    VkDeviceMemory vertexBufferMemory;
    void* vertexBufferMapped; // 매 프레임 업데이트를 위해 매핑 유지

    std::vector<VkBuffer> uniformBuffers;
    std::vector<VkDeviceMemory> uniformBuffersMemory;
    std::vector<void*> uniformBuffersMapped;

    VkDescriptorPool descriptorPool;
    VkDescriptorSet computeDescriptorSet;
    std::vector<VkDescriptorSet> descriptorSets;

    std::vector<VkCommandBuffer> commandBuffers;

    std::vector<VkSemaphore> imageAvailableSemaphores;
    std::vector<VkSemaphore> renderFinishedSemaphores;
    std::vector<VkFence> inFlightFences;
    uint32_t currentFrame = 0;

    const float stiffness = 1024.0f;

    bool framebufferResized = false;

    void initWindow() {
        glfwInit();

        glfwWindowHint(GLFW_CLIENT_API, GLFW_NO_API);

        window = glfwCreateWindow(WIDTH, HEIGHT, "Vulkan", nullptr, nullptr);
        glfwSetWindowUserPointer(window, this);
        glfwSetFramebufferSizeCallback(window, framebufferResizeCallback);
    }

    static void framebufferResizeCallback(GLFWwindow* window, int width, int height) {
        auto app = reinterpret_cast<HelloTriangleApplication*>(glfwGetWindowUserPointer(window));
        app->framebufferResized = true;
    }
    void initFinger() {
        // 3개의 관절(뼈) 세팅 (예: 손바닥 기점 -> 마디1 -> 마디2 -> 손끝)
        joints.resize(4);

        // Root (손바닥/너클)
        joints[0].localPos = glm::vec3(0.0f, 0.0f, 0.0f);
        joints[0].angle = glm::vec3(0.0f);

        // 관절 1 (첫 번째 마디, 길이 2.0)
        joints[1].localPos = glm::vec3(1.0f, 0.0f, 0.0f);
        joints[1].angle = glm::vec3(0.0f);
        // 관절 2 (두 번째 마디, 길이 1.5)
        joints[2].localPos = glm::vec3(0.5f, 0.0f, 0.0f);
        joints[2].angle = glm::vec3(0.0f);

        // 끝점 (손가락 끝, 길이 1.0)
        joints[3].localPos = glm::vec3(0.25f, 0.0f, 0.0f);
        joints[3].angle = glm::vec3(0.0f);
        vertices.resize(8);
    }

    void initHand() {
        hand.resize(10); // 왼손 5개(0~4) + 오른손 5개(5~9)

        auto deg2rad = [](float flex, float ext, float abdMin, float abdMax, float twistMin, float twistMax) {
            return JointLimits{
                glm::vec2(glm::radians(-flex), glm::radians(ext)),
                glm::vec2(glm::radians(abdMin), glm::radians(abdMax)),
                glm::vec2(glm::radians(twistMin), glm::radians(twistMax))
            };
            };

        for (int h = 0; h < 2; h++) {
            for (int f = 0; f < 5; f++) {
                int i = h * 5 + f;
                hand[i].joints.resize(4);

                hand[i].joints[0].localPos = glm::vec3(0.0f, 0.0f, 0.0f);
                hand[i].joints[1].localPos = glm::vec3(1.0f, 0.0f, 0.0f);
                hand[i].joints[2].localPos = glm::vec3(0.5f, 0.0f, 0.0f);
                hand[i].joints[3].localPos = glm::vec3(0.25f, 0.0f, 0.0f);

                for (int j = 0; j < 4; j++) {
                    hand[i].joints[j].angle = glm::vec3(0.0f);
                }

                // [핵심] 왼손과 오른손의 해부학적 대칭 Z 오프셋 (손목 중심 기준)
                // 왼손: 엄지(+0.4) -> 새끼(-0.8)
                float zOffsetsL[5] = { 0.4f, 0.1f, -0.2f, -0.5f, -0.8f };
                // 오른손: 엄지(-0.4) -> 새끼(+0.8)
                float zOffsetsR[5] = { -0.4f, -0.1f, 0.2f, 0.5f, 0.8f };

                float zOff = (h == 0) ? zOffsetsL[f] : zOffsetsR[f];

                if (f == 0) {
                    // [엄지] 신전(펴는 방향) 여유를 넓혀 짧은 거리 타겟에서 베이스 관절이
                    // 과도하게 젖혀지지 않고도 자연스럽게 펴진 자세를 취할 수 있게 함.
                    // DIP(joint2)는 실제 연주 시 거의 펴진 채로 유지되므로 굽힘 범위를 좁힘
                    hand[i].joints[0].limits = deg2rad(50.0f, 50.0f, -40.0f, 40.0f, 0.0f, 15.0f);
                    hand[i].joints[1].limits = deg2rad(110.0f, 15.0f, 0.0f, 0.0f, 0.0f, 0.0f); // [실험] PIP는 문제삼지 않았으니 여유를 더 줌
                    hand[i].joints[2].limits = deg2rad(32.0f, 15.0f, 0.0f, 0.0f, 0.0f, 0.0f); // DIP는 요청대로 좁게 유지
                    hand[i].joints[3].limits = deg2rad(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].rootOffset = glm::vec3(0.0f, -0.2f, zOff);
                }
                else {
                    // [일반 손가락] 마찬가지로 신전 여유를 넓히고, DIP(joint2) 굽힘 범위를 좁힘.
                    // 검은 건반 대부분을 검지/약지(일반 손가락)가 담당하는데 외전(Y) 한계가
                    // ±20도로 너무 좁아 옆으로 충분히 못 뻗어 검은 건반을 못 맞추는 문제가 있었음
                    hand[i].joints[0].limits = deg2rad(90.0f, 20.0f, -35.0f, 35.0f, 0.0f, 0.0f);
                    hand[i].joints[1].limits = deg2rad(110.0f, 20.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[2].limits = deg2rad(32.0f, 15.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[3].limits = deg2rad(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].rootOffset = glm::vec3(0.0f, 0.0f, zOff);
                }
            }
        }
        vertices.resize(80);
    }

    void initPianoKeyboard() {
        const int lowestPitch = dataLowestPitch;   // 로드한 데이터의 최저음 (updateSongInfo 에서 계산)
        const int highestPitch = dataHighestPitch; // 로드한 데이터의 최고음

        const float whiteKeyWidth = kWhiteKeyWidth; // getKeyLayout()과 반드시 동일해야 함
        const float whiteKeyGap = 0.04f;
        const float blackKeyWidthRatio = 0.5f; // 실제 피아노 비율(흰 건반 대비 약 55%)에 가깝게

        const float whiteTopY = -0.5f; // getKeyPosition()의 흰 건반 pressY와 동일
        const float blackTopY = -0.35f; // getKeyPosition()의 검은 건반 pressY와 동일
        // getKeyPosition()의 pressX(흰 0.8 / 검은 1.3)가 건반 안쪽에 들어오도록 여유를 0.1로 맞춤.
        // 흰 건반은 손목 쪽 앞부분(작은 X)까지 길게, 검은 건반은 안쪽 깊은 부분(큰 X)에서 짧게 배치.
        const float whiteFrontX = 1.6f, whiteBackX = 0.5f;   // 길이 1.1
        const float blackFrontX = 1.4f, blackBackX = 0.9f;   // 길이 0.5, 흰 건반 뒤쪽 절반 안에 위치

        const glm::vec3 whiteColor(0.9f, 0.9f, 0.9f);
        const glm::vec3 blackColor(0.05f, 0.05f, 0.05f);

        auto addKeyQuad = [&](float centerZ, float halfWidth, float frontX, float backX, float y, const glm::vec3& color) {
            glm::vec3 p0(frontX, y, centerZ - halfWidth);
            glm::vec3 p1(frontX, y, centerZ + halfWidth);
            glm::vec3 p2(backX, y, centerZ + halfWidth);
            glm::vec3 p3(backX, y, centerZ - halfWidth);

            // 사각형 하나를 삼각형 2개로 구성 (Triangle List)
            vertices.push_back({ p0, color });
            vertices.push_back({ p1, color });
            vertices.push_back({ p2, color });

            vertices.push_back({ p0, color });
            vertices.push_back({ p2, color });
            vertices.push_back({ p3, color });
            };

        pianoKeyVertexOffset = static_cast<uint32_t>(vertices.size());

        // 흰 건반을 먼저 깔고 검은 건반을 위에 얹는다 (깊이 테스트로 자연스럽게 겹쳐 보임)
        for (int pitch = lowestPitch; pitch <= highestPitch; pitch++) {
            KeyLayout layout = getKeyLayout(pitch);
            if (!layout.isBlack) {
                addKeyQuad(layout.z, (whiteKeyWidth - whiteKeyGap) * 0.5f, whiteFrontX, whiteBackX, whiteTopY, whiteColor);
            }
        }
        for (int pitch = lowestPitch; pitch <= highestPitch; pitch++) {
            KeyLayout layout = getKeyLayout(pitch);
            if (layout.isBlack) {
                addKeyQuad(layout.z, whiteKeyWidth * blackKeyWidthRatio * 0.5f, blackFrontX, blackBackX, blackTopY, blackColor);
            }
        }

        pianoKeyVertexCount = static_cast<uint32_t>(vertices.size()) - pianoKeyVertexOffset;
    }

    void initVulkan() {
        createInstance();
        setupDebugMessenger();
        createSurface();
        pickPhysicalDevice();
        createLogicalDevice();
        createSwapChain();
        createImageViews();
        createDepthResources();
        createRenderPass();
        createRenderDescriptorSetLayout();
        createGraphicsPipeline();
        createDynamicVertexBuffer();
        createFramebuffers();
        createCommandPool();
        createUniformBuffers();
        createDescriptorPool();
        createRenderDescriptorSets();
        createCommandBuffers();
        createSyncObjects();
    }

    void mainLoop() {
        while (!glfwWindowShouldClose(window)) {
            glfwPollEvents();
            drawFrame();
        }

        vkDeviceWaitIdle(device);
    }

    void cleanupSwapChain() {
        for (auto framebuffer : swapChainFramebuffers) {
            vkDestroyFramebuffer(device, framebuffer, nullptr);
        }

        for (auto imageView : swapChainImageViews) {
            vkDestroyImageView(device, imageView, nullptr);
        }

        vkDestroySwapchainKHR(device, swapChain, nullptr);
    }

    void cleanup() {
        cleanupSwapChain();

        vkDestroyPipeline(device, graphicsPipeline, nullptr);
        vkDestroyPipeline(device, pianoKeyPipeline, nullptr);
        vkDestroyPipelineLayout(device, pipelineLayout, nullptr);
        vkDestroyRenderPass(device, renderPass, nullptr);

        vkDestroyImageView(device, depthImageView, nullptr);
        vkDestroyImage(device, depthImage, nullptr);
        vkFreeMemory(device, depthImageMemory, nullptr);

        for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
            vkDestroyBuffer(device, uniformBuffers[i], nullptr);
            vkFreeMemory(device, uniformBuffersMemory[i], nullptr);
        }
        vkDestroyBuffer(device, vertexBuffer, nullptr);
        vkFreeMemory(device, vertexBufferMemory, nullptr);

        vkDestroyDescriptorPool(device, descriptorPool, nullptr);
        vkDestroyDescriptorSetLayout(device, descriptorSetLayout, nullptr);

        for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
            vkDestroySemaphore(device, imageAvailableSemaphores[i], nullptr);
            vkDestroyFence(device, inFlightFences[i], nullptr);
        }

        for (auto semaphore : renderFinishedSemaphores) {
            vkDestroySemaphore(device, semaphore, nullptr);
        }
        vkDestroyCommandPool(device, commandPool, nullptr);
        vkDestroyDevice(device, nullptr);

        if (enableValidationLayers) {
            DestroyDebugUtilsMessengerEXT(instance, debugMessenger, nullptr);
        }

        vkDestroySurfaceKHR(instance, surface, nullptr);
        vkDestroyInstance(instance, nullptr);

        glfwDestroyWindow(window);

        glfwTerminate();
    }

    void recreateSwapChain() {
        int width = 0, height = 0;
        glfwGetFramebufferSize(window, &width, &height);
        while (width == 0 || height == 0) {
            glfwGetFramebufferSize(window, &width, &height);
            glfwWaitEvents();
        }

        vkDeviceWaitIdle(device);

        cleanupSwapChain();

        createSwapChain();
        createImageViews();
        createFramebuffers();
    }

    void createInstance() {
        if (enableValidationLayers && !checkValidationLayerSupport()) {
            throw std::runtime_error("validation layers requested, but not available!");
        }

        VkApplicationInfo appInfo{};
        appInfo.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        appInfo.pApplicationName = "Hello Triangle";
        appInfo.applicationVersion = VK_MAKE_VERSION(1, 0, 0);
        appInfo.pEngineName = "No Engine";
        appInfo.engineVersion = VK_MAKE_VERSION(1, 0, 0);
        appInfo.apiVersion = VK_API_VERSION_1_0;

        VkInstanceCreateInfo createInfo{};
        createInfo.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        createInfo.pApplicationInfo = &appInfo;

        auto extensions = getRequiredExtensions();
        createInfo.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
        createInfo.ppEnabledExtensionNames = extensions.data();

        VkDebugUtilsMessengerCreateInfoEXT debugCreateInfo{};
        if (enableValidationLayers) {
            createInfo.enabledLayerCount = static_cast<uint32_t>(validationLayers.size());
            createInfo.ppEnabledLayerNames = validationLayers.data();

            populateDebugMessengerCreateInfo(debugCreateInfo);
            createInfo.pNext = (VkDebugUtilsMessengerCreateInfoEXT*)&debugCreateInfo;
        }
        else {
            createInfo.enabledLayerCount = 0;

            createInfo.pNext = nullptr;
        }

        if (vkCreateInstance(&createInfo, nullptr, &instance) != VK_SUCCESS) {
            throw std::runtime_error("failed to create instance!");
        }
    }

    void populateDebugMessengerCreateInfo(VkDebugUtilsMessengerCreateInfoEXT& createInfo) {
        createInfo = {};
        createInfo.sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT;
        createInfo.messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_VERBOSE_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
        createInfo.messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
        createInfo.pfnUserCallback = debugCallback;
    }

    void setupDebugMessenger() {
        if (!enableValidationLayers) return;

        VkDebugUtilsMessengerCreateInfoEXT createInfo;
        populateDebugMessengerCreateInfo(createInfo);

        if (CreateDebugUtilsMessengerEXT(instance, &createInfo, nullptr, &debugMessenger) != VK_SUCCESS) {
            throw std::runtime_error("failed to set up debug messenger!");
        }
    }

    void createSurface() {
        if (glfwCreateWindowSurface(instance, window, nullptr, &surface) != VK_SUCCESS) {
            throw std::runtime_error("failed to create window surface!");
        }
    }

    void pickPhysicalDevice() {
        uint32_t deviceCount = 0;
        vkEnumeratePhysicalDevices(instance, &deviceCount, nullptr);

        if (deviceCount == 0) {
            throw std::runtime_error("failed to find GPUs with Vulkan support!");
        }

        std::vector<VkPhysicalDevice> devices(deviceCount);
        vkEnumeratePhysicalDevices(instance, &deviceCount, devices.data());

        for (const auto& device : devices) {
            if (isDeviceSuitable(device)) {
                physicalDevice = device;
                break;
            }
        }

        if (physicalDevice == VK_NULL_HANDLE) {
            throw std::runtime_error("failed to find a suitable GPU!");
        }
    }

    void createLogicalDevice() {
        QueueFamilyIndices indices = findQueueFamilies(physicalDevice);

        std::vector<VkDeviceQueueCreateInfo> queueCreateInfos;
        std::set<uint32_t> uniqueQueueFamilies = { indices.graphicsFamily.value(), indices.presentFamily.value() };

        float queuePriority = 1.0f;
        for (uint32_t queueFamily : uniqueQueueFamilies) {
            VkDeviceQueueCreateInfo queueCreateInfo{};
            queueCreateInfo.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
            queueCreateInfo.queueFamilyIndex = queueFamily;
            queueCreateInfo.queueCount = 1;
            queueCreateInfo.pQueuePriorities = &queuePriority;
            queueCreateInfos.push_back(queueCreateInfo);
        }

        VkPhysicalDeviceFeatures deviceFeatures{};

        VkDeviceCreateInfo createInfo{};
        createInfo.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;

        createInfo.queueCreateInfoCount = static_cast<uint32_t>(queueCreateInfos.size());
        createInfo.pQueueCreateInfos = queueCreateInfos.data();

        createInfo.pEnabledFeatures = &deviceFeatures;

        createInfo.enabledExtensionCount = static_cast<uint32_t>(deviceExtensions.size());
        createInfo.ppEnabledExtensionNames = deviceExtensions.data();

        if (enableValidationLayers) {
            createInfo.enabledLayerCount = static_cast<uint32_t>(validationLayers.size());
            createInfo.ppEnabledLayerNames = validationLayers.data();
        }
        else {
            createInfo.enabledLayerCount = 0;
        }

        if (vkCreateDevice(physicalDevice, &createInfo, nullptr, &device) != VK_SUCCESS) {
            throw std::runtime_error("failed to create logical device!");
        }

        vkGetDeviceQueue(device, indices.graphicsFamily.value(), 0, &graphicsQueue);
        vkGetDeviceQueue(device, indices.presentFamily.value(), 0, &presentQueue);
    }

    void createSwapChain() {
        SwapChainSupportDetails swapChainSupport = querySwapChainSupport(physicalDevice);

        VkSurfaceFormatKHR surfaceFormat = chooseSwapSurfaceFormat(swapChainSupport.formats);
        VkPresentModeKHR presentMode = chooseSwapPresentMode(swapChainSupport.presentModes);
        VkExtent2D extent = chooseSwapExtent(swapChainSupport.capabilities);

        uint32_t imageCount = swapChainSupport.capabilities.minImageCount + 1;
        if (swapChainSupport.capabilities.maxImageCount > 0 && imageCount > swapChainSupport.capabilities.maxImageCount) {
            imageCount = swapChainSupport.capabilities.maxImageCount;
        }

        VkSwapchainCreateInfoKHR createInfo{};
        createInfo.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
        createInfo.surface = surface;

        createInfo.minImageCount = imageCount;
        createInfo.imageFormat = surfaceFormat.format;
        createInfo.imageColorSpace = surfaceFormat.colorSpace;
        createInfo.imageExtent = extent;
        createInfo.imageArrayLayers = 1;
        createInfo.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;

        QueueFamilyIndices indices = findQueueFamilies(physicalDevice);
        uint32_t queueFamilyIndices[] = { indices.graphicsFamily.value(), indices.presentFamily.value() };

        if (indices.graphicsFamily != indices.presentFamily) {
            createInfo.imageSharingMode = VK_SHARING_MODE_CONCURRENT;
            createInfo.queueFamilyIndexCount = 2;
            createInfo.pQueueFamilyIndices = queueFamilyIndices;
        }
        else {
            createInfo.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
        }

        createInfo.preTransform = swapChainSupport.capabilities.currentTransform;
        createInfo.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        createInfo.presentMode = presentMode;
        createInfo.clipped = VK_TRUE;

        if (vkCreateSwapchainKHR(device, &createInfo, nullptr, &swapChain) != VK_SUCCESS) {
            throw std::runtime_error("failed to create swap chain!");
        }

        vkGetSwapchainImagesKHR(device, swapChain, &imageCount, nullptr);
        swapChainImages.resize(imageCount);
        vkGetSwapchainImagesKHR(device, swapChain, &imageCount, swapChainImages.data());

        swapChainImageFormat = surfaceFormat.format;
        swapChainExtent = extent;
    }

    void createImageViews() {
        swapChainImageViews.resize(swapChainImages.size());

        for (size_t i = 0; i < swapChainImages.size(); i++) {
            VkImageViewCreateInfo createInfo{};
            createInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
            createInfo.image = swapChainImages[i];
            createInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
            createInfo.format = swapChainImageFormat;
            createInfo.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
            createInfo.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
            createInfo.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
            createInfo.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
            createInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
            createInfo.subresourceRange.baseMipLevel = 0;
            createInfo.subresourceRange.levelCount = 1;
            createInfo.subresourceRange.baseArrayLayer = 0;
            createInfo.subresourceRange.layerCount = 1;

            if (vkCreateImageView(device, &createInfo, nullptr, &swapChainImageViews[i]) != VK_SUCCESS) {
                throw std::runtime_error("failed to create image views!");
            }
        }
    }

    void createDepthResources() {
        VkFormat depthFormat = VK_FORMAT_D32_SFLOAT;

        // 1. 이미지 생성
        createImage(swapChainExtent.width, swapChainExtent.height, depthFormat,
            VK_IMAGE_TILING_OPTIMAL, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, depthImage, depthImageMemory);

        // 2. 이미지 뷰 생성
        VkImageViewCreateInfo viewInfo{};
        viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        viewInfo.image = depthImage;
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = depthFormat;
        viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
        viewInfo.subresourceRange.baseMipLevel = 0;
        viewInfo.subresourceRange.levelCount = 1;
        viewInfo.subresourceRange.baseArrayLayer = 0;
        viewInfo.subresourceRange.layerCount = 1;

        if (vkCreateImageView(device, &viewInfo, nullptr, &depthImageView) != VK_SUCCESS) {
            throw std::runtime_error("failed to create depth image view!");
        }
    }

    // 헬퍼 함수 (기존 createBuffer와 유사하게 이미지 생성용으로 구현 필요)
    void createImage(uint32_t width, uint32_t height, VkFormat format, VkImageTiling tiling,
        VkImageUsageFlags usage, VkMemoryPropertyFlags properties,
        VkImage& image, VkDeviceMemory& imageMemory) {
        VkImageCreateInfo imageInfo{};
        imageInfo.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        imageInfo.imageType = VK_IMAGE_TYPE_2D;
        imageInfo.extent.width = width;
        imageInfo.extent.height = height;
        imageInfo.extent.depth = 1;
        imageInfo.mipLevels = 1;
        imageInfo.arrayLayers = 1;
        imageInfo.format = format;
        imageInfo.tiling = tiling;
        imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        imageInfo.usage = usage;
        imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
        imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

        vkCreateImage(device, &imageInfo, nullptr, &image);

        VkMemoryRequirements memRequirements;
        vkGetImageMemoryRequirements(device, image, &memRequirements);

        VkMemoryAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocInfo.allocationSize = memRequirements.size;
        allocInfo.memoryTypeIndex = findMemoryType(memRequirements.memoryTypeBits, properties);

        vkAllocateMemory(device, &allocInfo, nullptr, &imageMemory);
        vkBindImageMemory(device, image, imageMemory, 0);
    }

    void createRenderPass() {
        VkAttachmentDescription colorAttachment{};
        colorAttachment.format = swapChainImageFormat;
        colorAttachment.samples = VK_SAMPLE_COUNT_1_BIT;
        colorAttachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        colorAttachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        colorAttachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        colorAttachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        colorAttachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        colorAttachment.finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;

        VkAttachmentDescription depthAttachment{};
        depthAttachment.format = VK_FORMAT_D32_SFLOAT; // 선택한 포맷
        depthAttachment.samples = VK_SAMPLE_COUNT_1_BIT;
        depthAttachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;  // 매 프레임 초기화
        depthAttachment.storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        depthAttachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        depthAttachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        depthAttachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        depthAttachment.finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkAttachmentReference colorAttachmentRef{};
        colorAttachmentRef.attachment = 0;
        colorAttachmentRef.layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;

        VkAttachmentReference depthAttachmentRef{};
        depthAttachmentRef.attachment = 1; // 0번은 Color, 1번은 Depth
        depthAttachmentRef.layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkSubpassDescription subpass{};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &colorAttachmentRef;
        subpass.pDepthStencilAttachment = &depthAttachmentRef;

        VkSubpassDependency dependency{};
        dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
        dependency.dstSubpass = 0;
        dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
        dependency.srcAccessMask = 0;
        dependency.dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
        dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;

        std::array<VkAttachmentDescription, 2> attachments = { colorAttachment, depthAttachment };
        VkRenderPassCreateInfo renderPassInfo{};
        renderPassInfo.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        renderPassInfo.attachmentCount = static_cast<uint32_t>(attachments.size());
        renderPassInfo.pAttachments = attachments.data();
        renderPassInfo.subpassCount = 1;
        renderPassInfo.pSubpasses = &subpass;
        renderPassInfo.dependencyCount = 1;
        renderPassInfo.pDependencies = &dependency;

        if (vkCreateRenderPass(device, &renderPassInfo, nullptr, &renderPass) != VK_SUCCESS) {
            throw std::runtime_error("failed to create render pass!");
        }
    }

    void createRenderDescriptorSetLayout() {
        VkDescriptorSetLayoutBinding uboLayoutBinding{};
        uboLayoutBinding.binding = 0;
        uboLayoutBinding.descriptorCount = 1;
        uboLayoutBinding.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        uboLayoutBinding.pImmutableSamplers = nullptr;
        uboLayoutBinding.stageFlags = VK_SHADER_STAGE_VERTEX_BIT;

        VkDescriptorSetLayoutCreateInfo layoutInfo{};
        layoutInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        layoutInfo.bindingCount = 1;
        layoutInfo.pBindings = &uboLayoutBinding;

        if (vkCreateDescriptorSetLayout(device, &layoutInfo, nullptr, &descriptorSetLayout) != VK_SUCCESS) {
            throw std::runtime_error("failed to create render descriptor set layout!");
        }
    }

    void createGraphicsPipeline() {
        auto vertShaderCode = readFile("shaders/VertexShader.vert.spv");
        auto fragShaderCode = readFile("shaders/FragmentShader.frag.spv");

        VkShaderModule vertShaderModule = createShaderModule(vertShaderCode);
        VkShaderModule fragShaderModule = createShaderModule(fragShaderCode);

        VkPipelineShaderStageCreateInfo vertShaderStageInfo{};
        vertShaderStageInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        vertShaderStageInfo.stage = VK_SHADER_STAGE_VERTEX_BIT;
        vertShaderStageInfo.module = vertShaderModule;
        vertShaderStageInfo.pName = "main";

        VkPipelineShaderStageCreateInfo fragShaderStageInfo{};
        fragShaderStageInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        fragShaderStageInfo.stage = VK_SHADER_STAGE_FRAGMENT_BIT;
        fragShaderStageInfo.module = fragShaderModule;
        fragShaderStageInfo.pName = "main";

        VkPipelineShaderStageCreateInfo shaderStages[] = { vertShaderStageInfo, fragShaderStageInfo };

        VkPipelineVertexInputStateCreateInfo vertexInputInfo{};
        vertexInputInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO;

        VkVertexInputBindingDescription bindingDescription{};
        bindingDescription.binding = 0;
        bindingDescription.stride = sizeof(Vertex);
        bindingDescription.inputRate = VK_VERTEX_INPUT_RATE_VERTEX;

        std::array<VkVertexInputAttributeDescription, 2> attributeDescriptions{};
        // Location 0: Position
        attributeDescriptions[0].binding = 0;
        attributeDescriptions[0].location = 0;
        attributeDescriptions[0].format = VK_FORMAT_R32G32B32_SFLOAT;
        attributeDescriptions[0].offset = offsetof(Vertex, pos);
        // Location 1: Color
        attributeDescriptions[1].binding = 0;
        attributeDescriptions[1].location = 1;
        attributeDescriptions[1].format = VK_FORMAT_R32G32B32_SFLOAT;
        attributeDescriptions[1].offset = offsetof(Vertex, color);

        vertexInputInfo.vertexBindingDescriptionCount = 1;
        vertexInputInfo.pVertexBindingDescriptions = &bindingDescription;
        vertexInputInfo.vertexAttributeDescriptionCount = static_cast<uint32_t>(attributeDescriptions.size());
        vertexInputInfo.pVertexAttributeDescriptions = attributeDescriptions.data();

        VkPipelineInputAssemblyStateCreateInfo inputAssembly{};
        inputAssembly.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO;
        inputAssembly.topology = VK_PRIMITIVE_TOPOLOGY_LINE_STRIP;
        inputAssembly.primitiveRestartEnable = VK_FALSE;

        VkPipelineViewportStateCreateInfo viewportState{};
        viewportState.sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO;
        viewportState.viewportCount = 1;
        viewportState.scissorCount = 1;

        VkPipelineRasterizationStateCreateInfo rasterizer{};
        rasterizer.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO;
        rasterizer.depthClampEnable = VK_FALSE;
        rasterizer.rasterizerDiscardEnable = VK_FALSE;
        rasterizer.polygonMode = VK_POLYGON_MODE_FILL;
        rasterizer.lineWidth = 1.0f;
        rasterizer.cullMode = VK_CULL_MODE_BACK_BIT;
        rasterizer.frontFace = VK_FRONT_FACE_CLOCKWISE;
        rasterizer.depthBiasEnable = VK_FALSE;

        VkPipelineDepthStencilStateCreateInfo depthStencil{};
        depthStencil.sType = VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO;
        depthStencil.depthTestEnable = VK_TRUE;
        depthStencil.depthWriteEnable = VK_TRUE;
        depthStencil.depthCompareOp = VK_COMPARE_OP_LESS; // 앞의 것만 통과
        depthStencil.depthBoundsTestEnable = VK_FALSE;
        depthStencil.stencilTestEnable = VK_FALSE;

        VkPipelineMultisampleStateCreateInfo multisampling{};
        multisampling.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO;
        multisampling.sampleShadingEnable = VK_FALSE;
        multisampling.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;

        VkPipelineColorBlendAttachmentState colorBlendAttachment{};
        colorBlendAttachment.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
        colorBlendAttachment.blendEnable = VK_FALSE;

        VkPipelineColorBlendStateCreateInfo colorBlending{};
        colorBlending.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO;
        colorBlending.logicOpEnable = VK_FALSE;
        colorBlending.logicOp = VK_LOGIC_OP_COPY;
        colorBlending.attachmentCount = 1;
        colorBlending.pAttachments = &colorBlendAttachment;
        colorBlending.blendConstants[0] = 0.0f;
        colorBlending.blendConstants[1] = 0.0f;
        colorBlending.blendConstants[2] = 0.0f;
        colorBlending.blendConstants[3] = 0.0f;

        std::vector<VkDynamicState> dynamicStates = {
            VK_DYNAMIC_STATE_VIEWPORT,
            VK_DYNAMIC_STATE_SCISSOR
        };
        VkPipelineDynamicStateCreateInfo dynamicState{};
        dynamicState.sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO;
        dynamicState.dynamicStateCount = static_cast<uint32_t>(dynamicStates.size());
        dynamicState.pDynamicStates = dynamicStates.data();

        VkPipelineLayoutCreateInfo pipelineLayoutInfo{};
        pipelineLayoutInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        pipelineLayoutInfo.setLayoutCount = 1;
        pipelineLayoutInfo.pSetLayouts = &descriptorSetLayout;

        if (vkCreatePipelineLayout(device, &pipelineLayoutInfo, nullptr, &pipelineLayout) != VK_SUCCESS) {
            throw std::runtime_error("failed to create pipeline layout!");
        }

        VkGraphicsPipelineCreateInfo pipelineInfo{};
        pipelineInfo.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO;
        pipelineInfo.stageCount = 2;
        pipelineInfo.pStages = shaderStages;
        pipelineInfo.pVertexInputState = &vertexInputInfo;
        pipelineInfo.pInputAssemblyState = &inputAssembly;
        pipelineInfo.pViewportState = &viewportState;
        pipelineInfo.pRasterizationState = &rasterizer;
        pipelineInfo.pDepthStencilState = &depthStencil;
        pipelineInfo.pMultisampleState = &multisampling;
        pipelineInfo.pColorBlendState = &colorBlending;
        pipelineInfo.pDynamicState = &dynamicState;
        pipelineInfo.layout = pipelineLayout;
        pipelineInfo.renderPass = renderPass;
        pipelineInfo.subpass = 0;
        pipelineInfo.basePipelineHandle = VK_NULL_HANDLE;

        if (vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &pipelineInfo, nullptr, &graphicsPipeline) != VK_SUCCESS) {
            throw std::runtime_error("failed to create graphics pipeline!");
        }

        // 피아노 건반용 파이프라인: 선(Line) 대신 채워진 삼각형으로 렌더링
        VkPipelineInputAssemblyStateCreateInfo keyInputAssembly = inputAssembly;
        keyInputAssembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;

        VkPipelineRasterizationStateCreateInfo keyRasterizer = rasterizer;
        keyRasterizer.cullMode = VK_CULL_MODE_NONE; // 와인딩 순서와 무관하게 항상 보이도록

        VkGraphicsPipelineCreateInfo keyPipelineInfo = pipelineInfo;
        keyPipelineInfo.pInputAssemblyState = &keyInputAssembly;
        keyPipelineInfo.pRasterizationState = &keyRasterizer;

        if (vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &keyPipelineInfo, nullptr, &pianoKeyPipeline) != VK_SUCCESS) {
            throw std::runtime_error("failed to create piano key pipeline!");
        }

        vkDestroyShaderModule(device, fragShaderModule, nullptr);
        vkDestroyShaderModule(device, vertShaderModule, nullptr);
    }

    void createFramebuffers() {
        swapChainFramebuffers.resize(swapChainImageViews.size());

        for (size_t i = 0; i < swapChainImageViews.size(); i++) {
            std::array<VkImageView, 2> attachments = {
                swapChainImageViews[i],
                depthImageView
            };

            VkFramebufferCreateInfo framebufferInfo{};
            framebufferInfo.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
            framebufferInfo.renderPass = renderPass;
            framebufferInfo.attachmentCount = static_cast<uint32_t>(attachments.size());
            framebufferInfo.pAttachments = attachments.data();
            framebufferInfo.width = swapChainExtent.width;
            framebufferInfo.height = swapChainExtent.height;
            framebufferInfo.layers = 1;

            if (vkCreateFramebuffer(device, &framebufferInfo, nullptr, &swapChainFramebuffers[i]) != VK_SUCCESS) {
                throw std::runtime_error("failed to create framebuffer!");
            }
        }
    }

    void createDynamicVertexBuffer() {
        VkDeviceSize bufferSize = sizeof(Vertex) * vertices.size();

        // 매 프레임 CPU에서 데이터를 덮어씌워야 하므로 HOST_VISIBLE | HOST_COHERENT 사용
        createBuffer(bufferSize, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
            vertexBuffer, vertexBufferMemory);

        vkMapMemory(device, vertexBufferMemory, 0, bufferSize, 0, &vertexBufferMapped);
    }

    void createCommandPool() {
        QueueFamilyIndices queueFamilyIndices = findQueueFamilies(physicalDevice);

        VkCommandPoolCreateInfo poolInfo{};
        poolInfo.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        poolInfo.queueFamilyIndex = queueFamilyIndices.graphicsFamily.value();

        if (vkCreateCommandPool(device, &poolInfo, nullptr, &commandPool) != VK_SUCCESS) {
            throw std::runtime_error("failed to create graphics command pool!");
        }
    }

    void createUniformBuffers() {
        VkDeviceSize bufferSize = sizeof(UniformBufferObject);

        uniformBuffers.resize(MAX_FRAMES_IN_FLIGHT);
        uniformBuffersMemory.resize(MAX_FRAMES_IN_FLIGHT);
        uniformBuffersMapped.resize(MAX_FRAMES_IN_FLIGHT);

        for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
            createBuffer(bufferSize, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, uniformBuffers[i], uniformBuffersMemory[i]);

            vkMapMemory(device, uniformBuffersMemory[i], 0, bufferSize, 0, &uniformBuffersMapped[i]);
        }
    }

    void createDescriptorPool() {
        std::array<VkDescriptorPoolSize, 1> poolSizes{};
        poolSizes[0].type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        poolSizes[0].descriptorCount = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);

        VkDescriptorPoolCreateInfo poolInfo{};
        poolInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        poolInfo.poolSizeCount = static_cast<uint32_t>(poolSizes.size());
        poolInfo.pPoolSizes = poolSizes.data();

        poolInfo.maxSets = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT) + 1;

        if (vkCreateDescriptorPool(device, &poolInfo, nullptr, &descriptorPool) != VK_SUCCESS) {
            throw std::runtime_error("failed to create descriptor pool!");
        }
    }

    void createRenderDescriptorSets() {
        std::vector<VkDescriptorSetLayout> layouts(MAX_FRAMES_IN_FLIGHT, descriptorSetLayout);
        VkDescriptorSetAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        allocInfo.descriptorPool = descriptorPool;
        allocInfo.descriptorSetCount = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);
        allocInfo.pSetLayouts = layouts.data();

        descriptorSets.resize(MAX_FRAMES_IN_FLIGHT);
        if (vkAllocateDescriptorSets(device, &allocInfo, descriptorSets.data()) != VK_SUCCESS) {
            throw std::runtime_error("failed to allocate descriptor sets!");
        }

        for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
            VkDescriptorBufferInfo bufferInfo{};
            bufferInfo.buffer = uniformBuffers[i];
            bufferInfo.offset = 0;
            bufferInfo.range = sizeof(UniformBufferObject);

            std::array<VkWriteDescriptorSet, 1> descriptorWrites{};
            descriptorWrites[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
            descriptorWrites[0].dstSet = descriptorSets[i];
            descriptorWrites[0].dstBinding = 0;
            descriptorWrites[0].dstArrayElement = 0;
            descriptorWrites[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
            descriptorWrites[0].descriptorCount = 1;
            descriptorWrites[0].pBufferInfo = &bufferInfo;

            vkUpdateDescriptorSets(device, static_cast<uint32_t>(descriptorWrites.size()), descriptorWrites.data(), 0, nullptr);
        }
    }

    void createBuffer(VkDeviceSize size, VkBufferUsageFlags usage, VkMemoryPropertyFlags properties, VkBuffer& buffer, VkDeviceMemory& bufferMemory) {
        VkBufferCreateInfo bufferInfo{};
        bufferInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        bufferInfo.size = size;
        bufferInfo.usage = usage;
        bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

        if (vkCreateBuffer(device, &bufferInfo, nullptr, &buffer) != VK_SUCCESS) {
            throw std::runtime_error("failed to create buffer!");
        }

        VkMemoryRequirements memRequirements;
        vkGetBufferMemoryRequirements(device, buffer, &memRequirements);

        VkMemoryAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocInfo.allocationSize = memRequirements.size;
        allocInfo.memoryTypeIndex = findMemoryType(memRequirements.memoryTypeBits, properties);

        if (vkAllocateMemory(device, &allocInfo, nullptr, &bufferMemory) != VK_SUCCESS) {
            throw std::runtime_error("failed to allocate buffer memory!");
        }

        vkBindBufferMemory(device, buffer, bufferMemory, 0);
    }

    void copyBuffer(VkBuffer srcBuffer, VkBuffer dstBuffer, VkDeviceSize size) {
        VkCommandBufferAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandPool = commandPool;
        allocInfo.commandBufferCount = 1;

        VkCommandBuffer commandBuffer;
        vkAllocateCommandBuffers(device, &allocInfo, &commandBuffer);

        VkCommandBufferBeginInfo beginInfo{};
        beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;

        vkBeginCommandBuffer(commandBuffer, &beginInfo);

        VkBufferCopy copyRegion{};
        copyRegion.size = size;
        vkCmdCopyBuffer(commandBuffer, srcBuffer, dstBuffer, 1, &copyRegion);

        vkEndCommandBuffer(commandBuffer);

        VkSubmitInfo submitInfo{};
        submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submitInfo.commandBufferCount = 1;
        submitInfo.pCommandBuffers = &commandBuffer;

        vkQueueSubmit(graphicsQueue, 1, &submitInfo, VK_NULL_HANDLE);
        vkQueueWaitIdle(graphicsQueue);

        vkFreeCommandBuffers(device, commandPool, 1, &commandBuffer);
    }

    uint32_t findMemoryType(uint32_t typeFilter, VkMemoryPropertyFlags properties) {
        VkPhysicalDeviceMemoryProperties memProperties;
        vkGetPhysicalDeviceMemoryProperties(physicalDevice, &memProperties);

        for (uint32_t i = 0; i < memProperties.memoryTypeCount; i++) {
            if ((typeFilter & (1 << i)) && (memProperties.memoryTypes[i].propertyFlags & properties) == properties) {
                return i;
            }
        }

        throw std::runtime_error("failed to find suitable memory type!");
    }

    void createCommandBuffers() {
        commandBuffers.resize(MAX_FRAMES_IN_FLIGHT);

        VkCommandBufferAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        allocInfo.commandPool = commandPool;
        allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandBufferCount = (uint32_t)commandBuffers.size();

        if (vkAllocateCommandBuffers(device, &allocInfo, commandBuffers.data()) != VK_SUCCESS) {
            throw std::runtime_error("failed to allocate command buffers!");
        }
    }

    void recordCommandBuffer(VkCommandBuffer commandBuffer, uint32_t imageIndex) {
        VkCommandBufferBeginInfo beginInfo{};
        beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;

        if (vkBeginCommandBuffer(commandBuffer, &beginInfo) != VK_SUCCESS) {
            throw std::runtime_error("failed to begin recording command buffer!");
        }

        VkRenderPassBeginInfo renderPassInfo{};
        renderPassInfo.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
        renderPassInfo.renderPass = renderPass;
        renderPassInfo.framebuffer = swapChainFramebuffers[imageIndex];
        renderPassInfo.renderArea.offset = { 0, 0 };
        renderPassInfo.renderArea.extent = swapChainExtent;

        //VkClearValue clearColor = { {{0.0f, 0.0f, 0.0f, 1.0f}} };
        std::array<VkClearValue, 2> clearValues{};
        clearValues[0].color = { {0.0f, 0.0f, 0.0f, 1.0f} };
        clearValues[1].depthStencil = { 1.0f, 0 }; // 깊이 최대값(1.0)으로 초기화

        renderPassInfo.clearValueCount = static_cast<uint32_t>(clearValues.size());
        renderPassInfo.pClearValues = clearValues.data();

        vkCmdBeginRenderPass(commandBuffer, &renderPassInfo, VK_SUBPASS_CONTENTS_INLINE);

        VkViewport viewport{};
        viewport.x = 0.0f;
        viewport.y = 0.0f;
        viewport.width = (float)swapChainExtent.width;
        viewport.height = (float)swapChainExtent.height;
        viewport.minDepth = 0.0f;
        viewport.maxDepth = 1.0f;
        vkCmdSetViewport(commandBuffer, 0, 1, &viewport);

        VkRect2D scissor{};
        scissor.offset = { 0, 0 };
        scissor.extent = swapChainExtent;
        vkCmdSetScissor(commandBuffer, 0, 1, &scissor);

        VkBuffer vertexBuffers[] = { vertexBuffer };
        VkDeviceSize offsets[] = { 0 };
        vkCmdBindVertexBuffers(commandBuffer, 0, 1, vertexBuffers, offsets);

        // Descriptor set 바인딩 (MVP 매트릭스용)
        vkCmdBindDescriptorSets(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipelineLayout, 0, 1, &descriptorSets[currentFrame], 0, nullptr);

        // 0. 피아노 건반(흰/검은 건반) 그리기
        vkCmdBindPipeline(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pianoKeyPipeline);
        vkCmdDraw(commandBuffer, pianoKeyVertexCount, 1, pianoKeyVertexOffset, 0);

        vkCmdBindPipeline(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, graphicsPipeline);

        // 1. 손가락 10개 그리기 (각 4개의 정점 선으로 연결)
        for (int i = 0; i < 10; i++) {
            vkCmdDraw(commandBuffer, 4, 1, i * 4, 0);
        }

        // 2. 타겟 십자선 10개 그리기 (손가락 개수만큼 타겟 렌더링)
        for (int i = 0; i < 10; i++) {
            uint32_t targetBaseIndex = 40 + (i * 4);
            vkCmdDraw(commandBuffer, 2, 1, targetBaseIndex, 0);     // 가로선
            vkCmdDraw(commandBuffer, 2, 1, targetBaseIndex + 2, 0); // 세로선
        }

        vkCmdEndRenderPass(commandBuffer);
        if (vkEndCommandBuffer(commandBuffer) != VK_SUCCESS) {
            throw std::runtime_error("failed to record command buffer!");
        }
    }

    void createSyncObjects() {
        uint32_t imageCount = static_cast<uint32_t>(swapChainImages.size());

        imageAvailableSemaphores.resize(MAX_FRAMES_IN_FLIGHT);
        renderFinishedSemaphores.resize(imageCount);
        inFlightFences.resize(MAX_FRAMES_IN_FLIGHT);

        VkSemaphoreCreateInfo semaphoreInfo{};
        semaphoreInfo.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;

        VkFenceCreateInfo fenceInfo{};
        fenceInfo.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fenceInfo.flags = VK_FENCE_CREATE_SIGNALED_BIT;

        // Acquire용 세마포어와 Fence 생성
        for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
            vkCreateSemaphore(device, &semaphoreInfo, nullptr, &imageAvailableSemaphores[i]);
            vkCreateFence(device, &fenceInfo, nullptr, &inFlightFences[i]);
        }

        // RenderFinished용 세마포어 생성 (이미지당 1개)
        for (size_t i = 0; i < imageCount; i++) {
            vkCreateSemaphore(device, &semaphoreInfo, nullptr, &renderFinishedSemaphores[i]);
        }
    }

    void updateUniformBuffer(uint32_t currentImage, float time) {
        // static auto startTime = std::chrono::high_resolution_clock::now();
        // 
        // auto currentTime = std::chrono::high_resolution_clock::now();
        // float time = std::chrono::duration<float, std::chrono::seconds::period>(currentTime - startTime).count();

        UniformBufferObject ubo{};
        //ubo.model = glm::rotate(glm::mat4(1.0f), time * glm::radians(90.0f), glm::vec3(0.0f, 0.0f, 1.0f));
        ubo.model = glm::mat4(1.0f);
        //ubo.view = glm::lookAt(glm::vec3(0.0f, 0.0f, -4.0f), glm::vec3(0.0f, 0.0f, 0.0f), glm::vec3(0.0f, 1.0f, 0.0f));
        // 카메라를 두 손목의 중간 Z로 따라가게 함. 손목 자체가 이미 보간되어 움직이지만,
        // 한 손만 크게 도약할 때 화면이 덜 흔들리도록 한 번 더 부드럽게 보간
        static float lastCamTime = time;
        static float cameraZ = wristCenterZ;
        float camDt = glm::clamp(time - lastCamTime, 0.0f, 0.1f);
        lastCamTime = time;
        const float cameraFollowRate = 3.0f;
        cameraZ = glm::mix(cameraZ, wristCenterZ, 1.0f - std::exp(-cameraFollowRate * camDt));

        ubo.view = glm::lookAt(
            glm::vec3(-3.5f, 3.0f, cameraZ),  // 카메라 위치 (Eye): X축 뒤쪽, Y축 위쪽
            glm::vec3(1.0f, 0.0f, cameraZ),   // 바라보는 곳 (Center): 손가락들이 뻗어있는 중심
            glm::vec3(0.0f, 1.0f, 0.0f)       // 위쪽 방향 (Up)
        );
        //float camRadius = 3.5f;
        //float camX = 1.0f + sin(time * 0.5f) * camRadius;
        //float camZ = cos(time * 0.5f) * camRadius;
        //ubo.view = glm::lookAt(
        //    glm::vec3(camX, 2.0f, camZ),   // 카메라 위치 (원운동)
        //    glm::vec3(1.0f, 0.0f, 0.0f),   // 바라보는 곳
        //    glm::vec3(0.0f, 1.0f, 0.0f)    // 위쪽 방향
        //);
        ubo.proj = glm::perspective(glm::radians(45.0f), swapChainExtent.width / (float)swapChainExtent.height, 0.1f, 10.0f);
        ubo.proj[1][1] *= -1;

        memcpy(uniformBuffersMapped[currentImage], &ubo, sizeof(ubo));
    }

    void updateFABRIKinematics(float time) {
        // 1. 초기 위치 설정 (최초 1회만 실행하여 NaN 오류 방지)
        static bool initialized = false;
        if (!initialized) {
            vertices[0].pos = glm::vec3(0.0f, 0.0f, 0.0f);  // Root
            vertices[1].pos = glm::vec3(1.0f, 0.0f, 0.0f);  // Joint 1 (1.0)
            vertices[2].pos = glm::vec3(1.5f, 0.0f, 0.0f);  // Joint 2 (1.0 + 0.5)
            vertices[3].pos = glm::vec3(1.75f, 0.0f, 0.0f); // Tip     (1.5 + 0.25)
            initialized = true;
        }
        // 2. 뼈의 길이 배열 설정 (localPos의 크기)
        float lengths[3] = {
            glm::length(joints[1].localPos), // Root to Joint1 (1.0)
            glm::length(joints[2].localPos), // Joint1 to Joint2 (0.5)
            glm::length(joints[3].localPos)  // Joint2 to Tip   (0.25)
        };

        // 3. 목표 지점(Target) 설정
        // 시각적 확인을 위해 시간에 따라 상하좌우(8자 모양)로 움직이게 만듦
        glm::vec3 targetPos = glm::vec3(
            1.0f + sin(time * 1.5f) * 0.75f, // X축: 0.25 ~ 1.75 사이를 왕복 (거의 쫙 펴지는 구간 포함)
            cos(time * 2.0f) * 0.75f,        // Y축: -0.75 ~ 0.75 사이를 왕복
            0.0f
        );

        // 연산용 위치 배열 (이전 프레임의 위치에서 출발)
        glm::vec3 p[4];
        for (int i = 0; i < 4; i++) p[i] = vertices[i].pos;

        glm::vec3 rootPos = glm::vec3(0.0f, 0.0f, 0.0f); // 손바닥 기점은 고정

        // 4. FABRIK 알고리즘 수행
        int iterationLimit = 10;  // 반복 횟수 (보통 5~10회면 충분히 수렴함)
        float tolerance = 0.01f;  // 허용 오차

        for (int iter = 0; iter < iterationLimit; iter++) {
            // [탈출 조건] 끝점이 타겟에 충분히 가까워지면 연산 종료
            if (glm::distance(p[3], targetPos) < tolerance) break;

            // --- Backward Pass (끝점 -> Root 방향으로 당기기) ---
            p[3] = targetPos; // 끝점을 타겟에 억지로 맞춤
            for (int i = 2; i >= 0; i--) {
                // 현재 관절에서 다음 관절을 바라보는 방향 벡터 계산
                glm::vec3 dir = glm::normalize(p[i] - p[i + 1]);
                // 길이를 유지하며 현재 관절 위치 조정
                p[i] = p[i + 1] + dir * lengths[i];
            }

            // --- Forward Pass (Root -> 끝점 방향으로 밀어내기) ---
            p[0] = rootPos; // Root를 원래 위치에 억지로 맞춤
            for (int i = 1; i < 4; i++) {
                // 이전 관절에서 현재 관절을 바라보는 방향 벡터 계산
                glm::vec3 dir = glm::normalize(p[i] - p[i - 1]);
                // 길이를 유지하며 현재 관절 위치 조정
                p[i] = p[i - 1] + dir * lengths[i - 1];
            }
        }

        // 5. 계산된 위치를 렌더링용 정점 데이터에 적용
        for (size_t i = 0; i < vertices.size(); i++) {
            vertices[i].pos = p[i];
            vertices[i].color = glm::vec3(1.0f, 0.5f, 0.0f); // 주황색 뼈대
        }

        // 6. 타겟 위치에 십자선(+) 정점 추가
        float crossSize = 0.05f; // 십자선의 크기
        glm::vec3 targetColor = glm::vec3(0.0f, 1.0f, 0.0f); // 녹색

        // 가로선 (좌 -> 우)
        vertices[4].pos = targetPos + glm::vec3(-crossSize, 0.0f, 0.0f);
        vertices[4].color = targetColor;
        vertices[5].pos = targetPos + glm::vec3(crossSize, 0.0f, 0.0f);
        vertices[5].color = targetColor;

        // 세로선 (하 -> 상)
        vertices[6].pos = targetPos + glm::vec3(0.0f, -crossSize, 0.0f);
        vertices[6].color = targetColor;
        vertices[7].pos = targetPos + glm::vec3(0.0f, crossSize, 0.0f);
        vertices[7].color = targetColor;

        // Vertex Buffer 갱신 (GPU로 데이터 전송)
        memcpy(vertexBufferMapped, vertices.data(), sizeof(Vertex) * vertices.size());
    }

    void updateJacobianKinematics(float time, const std::vector<NoteEvent>& activeNotes) {
        // 프레임레이트와 무관한 보간을 위한 dt 계산 (긴 멈춤 후 손목이 순간이동하지 않도록 상한을 둠)
        static float lastTime = time;
        float dt = glm::clamp(time - lastTime, 0.0f, 0.1f);
        lastTime = time;

        // --- [손목 트래킹 로직 (포물선 움직임 추가)] ---
        static glm::vec3 targetLeftWrist = glm::vec3(0.0f, 0.3f, -1.2f);
        static glm::vec3 targetRightWrist = glm::vec3(0.0f, 0.3f, 1.2f);
        // 검은 건반 보정도 X/Z 타겟처럼 유지하여, 음 사이 짧은 틈에 손목이 꺼졌다 올라오지 않게 함
        static float leftBlackBias = 0.0f;
        static float rightBlackBias = 0.0f;

        float leftXSum = 0.0f, rightXSum = 0.0f;
        float leftZSum = 0.0f, rightZSum = 0.0f;
        float leftYSum = 0.0f, rightYSum = 0.0f;
        int leftCount = 0, rightCount = 0;

        for (const auto& note : activeNotes) {
            glm::vec3 keyPos = getKeyPosition(note.pitch);

            // 손목을 건반 중앙이 아니라 "이 손가락의 뿌리가 건반 바로 위에 오는 위치"에 둠.
            // (건반 Z 평균에 두면 해당 손가락이 자기 rootOffset(최대 0.8)만큼 옆으로 뻗어야 했음)
            float rootOffsetZ = 0.0f;
            if (note.finger >= 1 && note.finger <= 5) {
                int fingerIdx = (note.hand * 5) + (note.finger - 1);
                rootOffsetZ = hand[fingerIdx].rootOffset.z;
            }
            float wristZForThisFinger = keyPos.z - rootOffsetZ;

            if (note.hand == 0) { leftXSum += keyPos.x; leftZSum += wristZForThisFinger; leftYSum += keyPos.y; leftCount++; }
            else { rightXSum += keyPos.x; rightZSum += wristZForThisFinger; rightYSum += keyPos.y; rightCount++; }
        }

        // 손목이 누르는 건반 쪽으로 미리 다가가야 손가락이 거의 다 펴지지 않고 자연스럽게 굽혀짐
        // (손가락에게는 wristReachMargin 만큼의 거리만 남겨서 뻗도록 함)
        // 검은 건반은 더 안쪽(X+)에 있지만, 음마다 손목 전체가 0.5씩 앞뒤로 튀지 않도록
        // 흰 건반 기준 위치 대비 차이의 일부만 손목에 반영하고 나머지는 손가락이 뻗어서 처리
        const float wristReachMargin = 0.8f; // 손목이 건반에 너무 붙어 보이지 않도록 여유를 늘림
        const float whiteKeyPressX = 0.8f;
        const float blackKeyWristReach = 0.3f;
        auto wristXFromAvgKeyX = [&](float avgKeyX) {
            return whiteKeyPressX + (avgKeyX - whiteKeyPressX) * blackKeyWristReach - wristReachMargin;
        };
        if (leftCount > 0) targetLeftWrist.x = wristXFromAvgKeyX(leftXSum / leftCount);
        if (rightCount > 0) targetRightWrist.x = wristXFromAvgKeyX(rightXSum / rightCount);

        if (leftCount > 0) targetLeftWrist.z = (leftZSum / leftCount);
        if (rightCount > 0) targetRightWrist.z = (rightZSum / rightCount);

        // 검은 건반 비중이 높을수록 손목을 아주 살짝 들어올리는 작은 보정치
        // (getKeyPosition의 흰 건반 기준 pressY 대비 얼마나 높은 위치인지로 계산)
        const float whiteKeyPressY = -0.5f;
        const float blackKeyWristLift = 0.3f; // 작은 오프셋 가중치 (건반 높이차 0.15의 30%만 반영)
        if (leftCount > 0) leftBlackBias = (leftYSum / leftCount - whiteKeyPressY) * blackKeyWristLift;
        if (rightCount > 0) rightBlackBias = (rightYSum / rightCount - whiteKeyPressY) * blackKeyWristLift;

        static glm::vec3 currentLeftWrist = targetLeftWrist;
        static glm::vec3 currentRightWrist = targetRightWrist;

        // 지수 감쇠 보간: alpha = 1 - exp(-rate * dt)
        // (rate 값은 기존 60FPS 기준 프레임당 0.12 / 0.15 와 같은 체감 속도가 되도록 맞춤)
        const float wristMoveRate = 7.7f;
        const float wristLiftRate = 9.75f;
        float wristMoveAlpha = 1.0f - std::exp(-wristMoveRate * dt);
        float wristLiftAlpha = 1.0f - std::exp(-wristLiftRate * dt);

        // 1. X축(앞뒤 뻗는 방향) / Z축(좌우) 이동 보간
        currentLeftWrist.x = glm::mix(currentLeftWrist.x, targetLeftWrist.x, wristMoveAlpha);
        currentRightWrist.x = glm::mix(currentRightWrist.x, targetRightWrist.x, wristMoveAlpha);
        currentLeftWrist.z = glm::mix(currentLeftWrist.z, targetLeftWrist.z, wristMoveAlpha);
        currentRightWrist.z = glm::mix(currentRightWrist.z, targetRightWrist.z, wristMoveAlpha);

        // 2. Y축(상하) 아치형 곡선 + 검은 건반 보정: 타겟과의 거리가 멀수록, 검은 건반을 누를수록 손목을 위로 들어올림
        // (좌우 이동뿐 아니라 앞뒤 이동 중에도 들리도록 XZ 평면 거리를 사용)
        float baseWristY = 0.1f; // 건반 위로 손목이 과하게 뜨지 않도록 낮춤 (기존 0.3f)
        float arcMultiplier = 0.2f; // 손목이 들리는 높이 가중치
        auto remainingTravel = [](const glm::vec3& target, const glm::vec3& current) {
            return glm::length(glm::vec2(target.x - current.x, target.z - current.z));
        };
        float targetY_L = baseWristY + remainingTravel(targetLeftWrist, currentLeftWrist) * arcMultiplier + leftBlackBias;
        float targetY_R = baseWristY + remainingTravel(targetRightWrist, currentRightWrist) * arcMultiplier + rightBlackBias;

        currentLeftWrist.y = glm::mix(currentLeftWrist.y, targetY_L, wristLiftAlpha);
        currentRightWrist.y = glm::mix(currentRightWrist.y, targetY_R, wristLiftAlpha);

        wristCenterZ = (currentLeftWrist.z + currentRightWrist.z) * 0.5f;


        // --- [FK 계산 람다] ---
        auto computeFK = [&](int fingerIdx) {
            glm::vec3 wristPos = (fingerIdx < 5) ? currentLeftWrist : currentRightWrist;
            glm::mat4 globalTransform = glm::translate(glm::mat4(1.0f), wristPos + hand[fingerIdx].rootOffset);

            hand[fingerIdx].joints[0].pos = glm::vec3(globalTransform[3]);
            hand[fingerIdx].joints[0].globalTransform = globalTransform;

            for (int i = 0; i < 3; i++) {
                glm::mat4 R = glm::mat4(1.0f);
                R = glm::rotate(R, hand[fingerIdx].joints[i].angle.y, glm::vec3(0.0f, 1.0f, 0.0f));
                R = glm::rotate(R, hand[fingerIdx].joints[i].angle.x, glm::vec3(0.0f, 0.0f, 1.0f));
                R = glm::rotate(R, hand[fingerIdx].joints[i].angle.z, glm::vec3(1.0f, 0.0f, 0.0f));

                glm::mat4 T = glm::translate(glm::mat4(1.0f), hand[fingerIdx].joints[i + 1].localPos);
                globalTransform = globalTransform * R * T;

                hand[fingerIdx].joints[i + 1].pos = glm::vec3(globalTransform[3]);
                hand[fingerIdx].joints[i + 1].globalTransform = globalTransform;
            }
            };

        // 2. 각 손가락별 C코드와 F코드 타겟 위치 정의
        // glm::vec3 targetsC[5];
        // glm::vec3 targetsF[5];
        // 
        // float shiftZ = -2.0f;
        // float pressX = 1.3f;
        // float liftX = 1.25f;
        // float pressY = -0.5f; // 건반을 누른 상태의 높이
        // float liftY = -0.1f;  // 건반에서 뗀 상태의 높이
        // //float baseZ[5] = { 0.6f, 0.6f, 0.2f, -0.2f, -0.6f }; // 손가락별 기본 Z 위치
        // 
        // float keyC = -0.6f + shiftZ;
        // float keyD = -0.4f + shiftZ;
        // float keyE = -0.2f + shiftZ;
        // float keyF = 0.0f + shiftZ;
        // float keyG = 0.2f + shiftZ;
        // float keyA = 0.4f + shiftZ;
        // 
        // // [C 코드] 5-3-1 운지법 (새끼:C, 중지:E, 엄지:G)
        // targetsC[0] = glm::vec3(pressX, pressY, keyG); // [0] 엄지: G (누름)
        // targetsC[1] = glm::vec3(liftX, liftY, keyF); // [1] 검지: F (뗌)
        // targetsC[2] = glm::vec3(pressX, pressY, keyE); // [2] 중지: E (누름)
        // targetsC[3] = glm::vec3(liftX, liftY, keyD); // [3] 약지: D (뗌)
        // targetsC[4] = glm::vec3(pressX, pressY, keyC); // [4] 새끼: C (누름)
        // 
        // // [F 코드] 5-2-1 운지법 (새끼:C, 검지:F, 엄지:A)
        // targetsF[0] = glm::vec3(pressX, pressY, keyA); // [0] 엄지: A (누름)
        // targetsF[1] = glm::vec3(pressX, pressY, keyF); // [1] 검지: F (누름)
        // targetsF[2] = glm::vec3(liftX, liftY, keyE); // [2] 중지: E (뗌)
        // targetsF[3] = glm::vec3(liftX, liftY, keyD); // [3] 약지: D (뗌)
        // targetsF[4] = glm::vec3(pressX, pressY, keyC); // [4] 새끼: C (누름)
        // 
        // // 현재 시간에 맞는 목표 위치 보간(Interpolation)
        // glm::vec3 currentTargets[5];
        // float fingerLiftArc = std::sin(t * 3.141592f) * 0.35f;
        // 
        // for (int i = 0; i < 5; i++) {
        //     currentTargets[i] = glm::mix(targetsC[i], targetsF[i], blend);
        //     currentTargets[i].y += fingerLiftArc;
        // }

        // --- [손가락 타겟 로직 (프레임 간 보간 및 낙하 궤적 추가)] ---
        glm::vec3 desiredTargets[10]; // 손가락이 최종적으로 가야 할 목표 지점

        // 1. 대기 상태 위치 설정. 거의 일자로 편 상태(-0.1)는 관절이 굽힘 쪽으로만 넉넉하고
        // 펴는 쪽 여유가 거의 없는 이 손가락 구조에서 오히려 수렴이 안 되는 어려운 자세였음
        // (디버그로 확인: err~0.3 고착). 실제 이완된 손가락처럼 자연스럽게 아래로 굽은
        // 자세를 목표로 삼아 관절 한계와 맞는 자세로 바꿈.
        float restX = 0.9f;
        float restY = -0.35f;
        for (int i = 0; i < 10; i++) {
            glm::vec3 wristPos = (i < 5) ? currentLeftWrist : currentRightWrist;
            desiredTargets[i] = wristPos + hand[i].rootOffset + glm::vec3(restX, restY, 0.0f);
        }

        // 2. 활성화된 Note 위치로 덮어쓰기
        for (const auto& note : activeNotes) {
            if (note.finger >= 1 && note.finger <= 5) {
                int fingerIdx = (note.hand * 5) + (note.finger - 1);
                desiredTargets[fingerIdx] = getKeyPosition(note.pitch);
            }
        }

        // 3. 실제 IK가 추적할 부드러운 타겟 (Smoothed Targets)
        static glm::vec3 smoothedTargets[10];
        static bool firstTargetInit = true;
        if (firstTargetInit) {
            for (int i = 0; i < 10; i++) smoothedTargets[i] = desiredTargets[i];
            firstTargetInit = false;
        }

        for (int i = 0; i < 10; i++) {
            float fingerLerpSpeed = 0.25f; // 손가락 이동 속도 (값이 낮을수록 묵직함)

            // 기본 위치 보간
            glm::vec3 nextPos = glm::mix(smoothedTargets[i], desiredTargets[i], fingerLerpSpeed);

            // 이동 거리가 남아있을 때 위로 살짝 뜨도록 Y축 가중치 부여 (건반을 내리치는 모션)
            float dist = glm::distance(smoothedTargets[i], desiredTargets[i]);
            nextPos.y += dist * 0.08f;

            smoothedTargets[i] = nextPos;
        }

        // 3. 자코비안 IK 알고리즘 적용
        for (int fingerIdx = 0; fingerIdx < 10; fingerIdx++) {

            // [진단 결과] 이전 프레임의 각도로 웜스타트하면 한 번 나쁜 국소 최적해(관절이
            // 한계각도에 고정됨)에 빠진 뒤 영원히 못 벗어남 (반복마다 살짝 당기는 방식도
            // 매 반복 주 목표와 경합하여 오히려 수렴을 방해함, 직접 확인함: 오차가 더 커짐).
            // 매 프레임 일자 자세(0도)에서 새로 풀어서 나쁜 상태가 누적되지 않도록 함.
            for (int i = 0; i < 3; i++) {
                hand[fingerIdx].joints[i].angle = glm::vec3(0.0f);
            }

            int iterationLimit = 40;
            float tolerance = 0.01f;
            glm::vec3 targetPos = smoothedTargets[fingerIdx]; // 개별 손가락 타겟 적용
            for (int iter = 0; iter < iterationLimit; iter++) {
                computeFK(fingerIdx);

                glm::vec3 endEffector = hand[fingerIdx].joints[3].pos;
                glm::vec3 error = targetPos - endEffector;

                if (glm::length(error) < tolerance) break;

                glm::vec3 J_cols[9];
                int dofIndex = 0;

                for (int i = 0; i < 3; i++) {
                    glm::vec3 p_i = hand[fingerIdx].joints[i].pos;
                    glm::mat4 globalRot = hand[fingerIdx].joints[i].globalTransform;

                    glm::mat4 ry = glm::rotate(glm::mat4(1.0f), hand[fingerIdx].joints[i].angle.y, glm::vec3(0.0f, 1.0f, 0.0f));
                    glm::mat4 rz = glm::rotate(glm::mat4(1.0f), hand[fingerIdx].joints[i].angle.x, glm::vec3(0.0f, 0.0f, 1.0f));

                    glm::vec3 axisY = glm::normalize(glm::vec3(globalRot * glm::vec4(0.0f, 1.0f, 0.0f, 0.0f)));
                    glm::vec3 axisX = glm::normalize(glm::vec3(globalRot * ry * glm::vec4(0.0f, 0.0f, 1.0f, 0.0f)));
                    glm::vec3 axisZ = glm::normalize(glm::vec3(globalRot * ry * rz * glm::vec4(1.0f, 0.0f, 0.0f, 0.0f)));

                    J_cols[dofIndex++] = glm::cross(axisX, endEffector - p_i);
                    J_cols[dofIndex++] = glm::cross(axisY, endEffector - p_i);
                    J_cols[dofIndex++] = glm::cross(axisZ, endEffector - p_i);
                }

                // glm::mat3 JJt = glm::mat3(0.0f);
                // for (int i = 0; i < 9; i++) {
                //     JJt += glm::outerProduct(J_cols[i], J_cols[i]);
                // }

                // float damping = 0.05f;
                // JJt += glm::mat3(1.0f) * (damping * damping);
                // 
                // glm::mat3 invJJt = glm::inverse(JJt);
                // glm::vec3 e_star = invJJt * error;
                // 
                // dofIndex = 0;
                // for (int i = 0; i < 3; i++) {
                //     glm::vec3 dTheta(
                //         glm::dot(J_cols[dofIndex], e_star),
                //         glm::dot(J_cols[dofIndex + 1], e_star),
                //         glm::dot(J_cols[dofIndex + 2], e_star)
                //     );
                // 
                //     float maxStep = 0.1f;
                //     float stepLen = glm::length(dTheta);
                //     if (stepLen > maxStep) {
                //         dTheta *= (maxStep / stepLen); // 방향은 유지하고 최대 길이만 제한
                //     }
                // 
                //     hand[fingerIdx].joints[i].angle.x += dTheta.x;
                //     hand[fingerIdx].joints[i].angle.y += dTheta.y;
                //     hand[fingerIdx].joints[i].angle.z += dTheta.z;
                //     dofIndex += 3;
                // 
                //     JointLimits& limits = hand[fingerIdx].joints[i].limits;
                //     hand[fingerIdx].joints[i].angle.x = std::clamp(hand[fingerIdx].joints[i].angle.x, limits.flexionExtension.x, limits.flexionExtension.y);
                //     hand[fingerIdx].joints[i].angle.y = std::clamp(hand[fingerIdx].joints[i].angle.y, limits.abductionAdduction.x, limits.abductionAdduction.y);
                //     hand[fingerIdx].joints[i].angle.z = std::clamp(hand[fingerIdx].joints[i].angle.z, limits.axialTwist.x, limits.axialTwist.y);
                // 
                //     //if (fingerIdx != 0 && (i == 1 || i == 2)) {
                //     //    hand[fingerIdx].joints[i].angle.x = std::max(-0.02f, hand[fingerIdx].joints[i].angle.x);
                //     //}
                // }
                float W_inv[9];
                int dofIndex_w = 0;
                for (int i = 0; i < 3; i++) {
                    JointLimits& limits = hand[fingerIdx].joints[i].limits;
                    glm::vec3 angle = hand[fingerIdx].joints[i].angle;

                    // 현재 각도가 한계치에 근접할수록 비용(W)을 급격히 늘려, W^-1 값을 0에 가깝게 만듦
                    auto calcWInv = [](float q, float min_q, float max_q) {
                        if (std::abs(max_q - min_q) < 1e-4f) return 0.0f; // 가동 불가 관절 (예: 엄지 외의 손가락 Z축)

                        float mid = (max_q + min_q) * 0.5f;
                        float range = (max_q - min_q) * 0.5f;
                        float normalized_q = (q - mid) / range; // -1.0 ~ 1.0 범위로 정규화

                        // 경계에 다가갈수록 급격히 증가하는 페널티 항 (요구사항 반영)
                        float penalty = std::pow(std::abs(normalized_q), 6.0f);
                        float w = 1.0f + 100.0f * penalty;
                        return 1.0f / w;
                        };

                    W_inv[dofIndex_w++] = calcWInv(angle.x, limits.flexionExtension.x, limits.flexionExtension.y);
                    W_inv[dofIndex_w++] = calcWInv(angle.y, limits.abductionAdduction.x, limits.abductionAdduction.y);
                    W_inv[dofIndex_w++] = calcWInv(angle.z, limits.axialTwist.x, limits.axialTwist.y);
                }

                // 2. Weighted DLS 매트릭스 계산 (J * W^-1 * J^T)
                glm::mat3 JWJt = glm::mat3(0.0f);
                for (int i = 0; i < 9; i++) {
                    JWJt += glm::outerProduct(J_cols[i], J_cols[i]) * W_inv[i];
                }

                // Damping 요소 추가 (특이점 회피)
                float damping = 0.05f;
                JWJt += glm::mat3(1.0f) * (damping * damping);

                glm::mat3 invJWJt = glm::inverse(JWJt);
                glm::vec3 e_star = invJWJt * error;

                // 3. dTheta 계산 (W^-1 * J^T * e_star). [버그 수정] 예전에는 관절마다 따로
                // maxStep으로 잘랐는데, 이러면 지렛대가 큰 joint0(길이 1.0)와 작은
                // joint2(길이 0.25)가 매 반복 "같은" 각도만큼만 움직이도록 강제되어, 원래
                // 가중 역행렬이 의도한 관절별 분배 비율이 깨짐. 그 결과 지렛대가 작은
                // joint1/2가 실제 필요한 것보다 훨씬 빨리 한계각도까지 밀려버리고, joint0는
                // 못 따라잡아 전체가 나쁜 국소해에 고정됨 (반복별 디버그로 직접 확인).
                // 9개 DOF 전체를 하나의 벡터로 보고 총 스텝 길이만 제한해 비율을 보존함.
                glm::vec3 dThetaPerJoint[3];
                dofIndex = 0;
                for (int i = 0; i < 3; i++) {
                    dThetaPerJoint[i] = glm::vec3(
                        W_inv[dofIndex] * glm::dot(J_cols[dofIndex], e_star),
                        W_inv[dofIndex + 1] * glm::dot(J_cols[dofIndex + 1], e_star),
                        W_inv[dofIndex + 2] * glm::dot(J_cols[dofIndex + 2], e_star)
                    );
                    dofIndex += 3;
                }

                float maxStep = 0.1f;
                float totalStepLenSq = glm::dot(dThetaPerJoint[0], dThetaPerJoint[0]) + glm::dot(dThetaPerJoint[1], dThetaPerJoint[1]) + glm::dot(dThetaPerJoint[2], dThetaPerJoint[2]);
                float totalStepLen = std::sqrt(totalStepLenSq);
                float scale = (totalStepLen > maxStep) ? (maxStep / totalStepLen) : 1.0f;

                for (int i = 0; i < 3; i++) {
                    hand[fingerIdx].joints[i].angle += dThetaPerJoint[i] * scale;

                    // 4. 안전장치: 연산 오차로 인한 범위 이탈을 막기 위한 최종 하드 클램프
                    JointLimits& limits = hand[fingerIdx].joints[i].limits;
                    hand[fingerIdx].joints[i].angle.x = std::clamp(hand[fingerIdx].joints[i].angle.x, limits.flexionExtension.x, limits.flexionExtension.y);
                    hand[fingerIdx].joints[i].angle.y = std::clamp(hand[fingerIdx].joints[i].angle.y, limits.abductionAdduction.x, limits.abductionAdduction.y);
                    hand[fingerIdx].joints[i].angle.z = std::clamp(hand[fingerIdx].joints[i].angle.z, limits.axialTwist.x, limits.axialTwist.y);
                }
            }
            computeFK(fingerIdx);
        }

        // 4. 렌더링용 Vertex 배열 데이터 매핑 
        for (int fingerIdx = 0; fingerIdx < 10; fingerIdx++) {
            for (int i = 0; i < 4; i++) {
                int vIdx = (fingerIdx * 4) + i;
                vertices[vIdx].pos = hand[fingerIdx].joints[i].pos;
                if (fingerIdx == 0 || fingerIdx == 5) vertices[vIdx].color = glm::vec3(0.0f, 1.0f, 0.0f);
                else vertices[vIdx].color = (fingerIdx < 5) ? glm::vec3(1.0f, 0.5f, 0.0f) : glm::vec3(0.0f, 0.5f, 1.0f);
            }
        }

        // 5. 타겟 십자선 5개 모두 정점 업데이트
        float crossSize = 0.03f;
        glm::vec3 targetColor = glm::vec3(1.0f, 0.2f, 0.2f); // 누르는 위치 시각화를 위해 붉은 계열

        for (int i = 0; i < 10; i++) {
            int vIdx = 40 + (i * 4);
            glm::vec3 tPos = smoothedTargets[i];

            // 가로선
            vertices[vIdx + 0].pos = tPos + glm::vec3(-crossSize, 0.0f, 0.0f); vertices[vIdx + 0].color = targetColor;
            vertices[vIdx + 1].pos = tPos + glm::vec3(crossSize, 0.0f, 0.0f);  vertices[vIdx + 1].color = targetColor;
            // 세로선
            vertices[vIdx + 2].pos = tPos + glm::vec3(0.0f, 0.0f, -crossSize); vertices[vIdx + 2].color = targetColor;
            vertices[vIdx + 3].pos = tPos + glm::vec3(0.0f, 0.0f, crossSize);  vertices[vIdx + 3].color = targetColor;
        }

        memcpy(vertexBufferMapped, vertices.data(), sizeof(Vertex) * vertices.size());
    }

    void drawFrame() {
        vkWaitForFences(device, 1, &inFlightFences[currentFrame], VK_TRUE, UINT64_MAX);

        uint32_t imageIndex;
        VkResult result = vkAcquireNextImageKHR(device, swapChain, UINT64_MAX, imageAvailableSemaphores[currentFrame], VK_NULL_HANDLE, &imageIndex);

        if (result == VK_ERROR_OUT_OF_DATE_KHR) {
            recreateSwapChain();
            return;
        }
        else if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
            throw std::runtime_error("failed to acquire swap chain image!");
        }

        //updateFABRIKinematics(time);
        static auto startTime = std::chrono::high_resolution_clock::now();
        auto currentTime = std::chrono::high_resolution_clock::now();
        float time = std::chrono::duration<float, std::chrono::seconds::period>(currentTime - startTime).count();

        std::vector<NoteEvent> currentNotes = getActiveNotesForCurrentTime(time);

		updateJacobianKinematics(time, currentNotes);
        updateUniformBuffer(currentFrame, time);

        vkResetFences(device, 1, &inFlightFences[currentFrame]);

        vkResetCommandBuffer(commandBuffers[currentFrame], /*VkCommandBufferResetFlagBits*/ 0);
        recordCommandBuffer(commandBuffers[currentFrame], imageIndex);

        VkSubmitInfo submitInfo{};
        submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;

        VkSemaphore waitSemaphores[] = { imageAvailableSemaphores[currentFrame] };
        VkPipelineStageFlags waitStages[] = { VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT };
        submitInfo.waitSemaphoreCount = 1;
        submitInfo.pWaitSemaphores = waitSemaphores;
        submitInfo.pWaitDstStageMask = waitStages;

        submitInfo.commandBufferCount = 1;
        submitInfo.pCommandBuffers = &commandBuffers[currentFrame];

        VkSemaphore signalSemaphores[] = { renderFinishedSemaphores[imageIndex] };
        submitInfo.signalSemaphoreCount = 1;
        submitInfo.pSignalSemaphores = signalSemaphores;

        if (vkQueueSubmit(graphicsQueue, 1, &submitInfo, inFlightFences[currentFrame]) != VK_SUCCESS) {
            throw std::runtime_error("failed to submit draw command buffer!");
        }

        VkPresentInfoKHR presentInfo{};
        presentInfo.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;

        presentInfo.waitSemaphoreCount = 1;
        presentInfo.pWaitSemaphores = signalSemaphores;

        VkSwapchainKHR swapChains[] = { swapChain };
        presentInfo.swapchainCount = 1;
        presentInfo.pSwapchains = swapChains;

        presentInfo.pImageIndices = &imageIndex;

        result = vkQueuePresentKHR(presentQueue, &presentInfo);

        if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR || framebufferResized) {
            framebufferResized = false;
            recreateSwapChain();
        }
        else if (result != VK_SUCCESS) {
            throw std::runtime_error("failed to present swap chain image!");
        }

        currentFrame = (currentFrame + 1) % MAX_FRAMES_IN_FLIGHT;
    }

    VkShaderModule createShaderModule(const std::vector<char>& code) {
        VkShaderModuleCreateInfo createInfo{};
        createInfo.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        createInfo.codeSize = code.size();
        createInfo.pCode = reinterpret_cast<const uint32_t*>(code.data());

        VkShaderModule shaderModule;
        if (vkCreateShaderModule(device, &createInfo, nullptr, &shaderModule) != VK_SUCCESS) {
            throw std::runtime_error("failed to create shader module!");
        }

        return shaderModule;
    }

    VkSurfaceFormatKHR chooseSwapSurfaceFormat(const std::vector<VkSurfaceFormatKHR>& availableFormats) {
        for (const auto& availableFormat : availableFormats) {
            if (availableFormat.format == VK_FORMAT_B8G8R8A8_SRGB && availableFormat.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) {
                return availableFormat;
            }
        }

        return availableFormats[0];
    }

    VkPresentModeKHR chooseSwapPresentMode(const std::vector<VkPresentModeKHR>& availablePresentModes) {
        for (const auto& availablePresentMode : availablePresentModes) {
            if (availablePresentMode == VK_PRESENT_MODE_MAILBOX_KHR) {
                return availablePresentMode;
            }
        }

        return VK_PRESENT_MODE_FIFO_KHR;
    }

    VkExtent2D chooseSwapExtent(const VkSurfaceCapabilitiesKHR& capabilities) {
        if (capabilities.currentExtent.width != std::numeric_limits<uint32_t>::max()) {
            return capabilities.currentExtent;
        }
        else {
            int width, height;
            glfwGetFramebufferSize(window, &width, &height);

            VkExtent2D actualExtent = {
                static_cast<uint32_t>(width),
                static_cast<uint32_t>(height)
            };

            actualExtent.width = std::clamp(actualExtent.width, capabilities.minImageExtent.width, capabilities.maxImageExtent.width);
            actualExtent.height = std::clamp(actualExtent.height, capabilities.minImageExtent.height, capabilities.maxImageExtent.height);

            return actualExtent;
        }
    }

    SwapChainSupportDetails querySwapChainSupport(VkPhysicalDevice device) {
        SwapChainSupportDetails details;

        vkGetPhysicalDeviceSurfaceCapabilitiesKHR(device, surface, &details.capabilities);

        uint32_t formatCount;
        vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface, &formatCount, nullptr);

        if (formatCount != 0) {
            details.formats.resize(formatCount);
            vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface, &formatCount, details.formats.data());
        }

        uint32_t presentModeCount;
        vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface, &presentModeCount, nullptr);

        if (presentModeCount != 0) {
            details.presentModes.resize(presentModeCount);
            vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface, &presentModeCount, details.presentModes.data());
        }

        return details;
    }

    bool isDeviceSuitable(VkPhysicalDevice device) {
        QueueFamilyIndices indices = findQueueFamilies(device);

        bool extensionsSupported = checkDeviceExtensionSupport(device);

        bool swapChainAdequate = false;
        if (extensionsSupported) {
            SwapChainSupportDetails swapChainSupport = querySwapChainSupport(device);
            swapChainAdequate = !swapChainSupport.formats.empty() && !swapChainSupport.presentModes.empty();
        }

        return indices.isComplete() && extensionsSupported && swapChainAdequate;
    }

    bool checkDeviceExtensionSupport(VkPhysicalDevice device) {
        uint32_t extensionCount;
        vkEnumerateDeviceExtensionProperties(device, nullptr, &extensionCount, nullptr);

        std::vector<VkExtensionProperties> availableExtensions(extensionCount);
        vkEnumerateDeviceExtensionProperties(device, nullptr, &extensionCount, availableExtensions.data());

        std::set<std::string> requiredExtensions(deviceExtensions.begin(), deviceExtensions.end());

        for (const auto& extension : availableExtensions) {
            requiredExtensions.erase(extension.extensionName);
        }

        return requiredExtensions.empty();
    }

    QueueFamilyIndices findQueueFamilies(VkPhysicalDevice device) {
        QueueFamilyIndices indices;

        uint32_t queueFamilyCount = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(device, &queueFamilyCount, nullptr);

        std::vector<VkQueueFamilyProperties> queueFamilies(queueFamilyCount);
        vkGetPhysicalDeviceQueueFamilyProperties(device, &queueFamilyCount, queueFamilies.data());

        int i = 0;
        for (const auto& queueFamily : queueFamilies) {
            if (queueFamily.queueFlags & VK_QUEUE_GRAPHICS_BIT) {
                indices.graphicsFamily = i;
            }

            VkBool32 presentSupport = false;
            vkGetPhysicalDeviceSurfaceSupportKHR(device, i, surface, &presentSupport);

            if (presentSupport) {
                indices.presentFamily = i;
            }

            if (indices.isComplete()) {
                break;
            }

            i++;
        }

        return indices;
    }

    std::vector<const char*> getRequiredExtensions() {
        uint32_t glfwExtensionCount = 0;
        const char** glfwExtensions;
        glfwExtensions = glfwGetRequiredInstanceExtensions(&glfwExtensionCount);

        std::vector<const char*> extensions(glfwExtensions, glfwExtensions + glfwExtensionCount);

        if (enableValidationLayers) {
            extensions.push_back(VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
        }

        return extensions;
    }

    bool checkValidationLayerSupport() {
        uint32_t layerCount;
        vkEnumerateInstanceLayerProperties(&layerCount, nullptr);

        std::vector<VkLayerProperties> availableLayers(layerCount);
        vkEnumerateInstanceLayerProperties(&layerCount, availableLayers.data());

        for (const char* layerName : validationLayers) {
            bool layerFound = false;

            for (const auto& layerProperties : availableLayers) {
                if (strcmp(layerName, layerProperties.layerName) == 0) {
                    layerFound = true;
                    break;
                }
            }

            if (!layerFound) {
                return false;
            }
        }

        return true;
    }

    static std::vector<char> readFile(const std::string& filename) {
        std::ifstream file(filename, std::ios::ate | std::ios::binary);

        if (!file.is_open()) {
            throw std::runtime_error("failed to open file!");
        }

        size_t fileSize = (size_t)file.tellg();
        std::vector<char> buffer(fileSize);

        file.seekg(0);
        file.read(buffer.data(), fileSize);

        file.close();

        return buffer;
    }

    static VKAPI_ATTR VkBool32 VKAPI_CALL debugCallback(VkDebugUtilsMessageSeverityFlagBitsEXT messageSeverity, VkDebugUtilsMessageTypeFlagsEXT messageType, const VkDebugUtilsMessengerCallbackDataEXT* pCallbackData, void* pUserData) {
        std::cerr << "validation layer: " << pCallbackData->pMessage << std::endl;

        return VK_FALSE;
    }
};

int main() {
    HelloTriangleApplication app;

    try {
        app.run();
    }
    catch (const std::exception& e) {
        std::cerr << e.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
