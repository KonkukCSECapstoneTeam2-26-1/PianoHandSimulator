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
};

glm::vec3 getKeyPosition(int pitch) {
    // 예시: MIDI 60 (Middle C)를 Z = 0.0f 기준으로 잡고 넓이를 계산
    float keyWidth = 0.2f;
    float zPos = (pitch - 60) * keyWidth;

    // 검은 건반(샵/플랫)인지 판별하여 X(건반 깊이) 및 Y(건반 높이) 차이를 두면 더 현실적입니다.
    // 여기서는 단순화된 위치를 반환합니다.
    float pressX = 1.3f;
    float pressY = -0.5f;

    return glm::vec3(pressX, pressY, zPos);
}

// 전체 MIDI 노트 데이터를 담아둘 멤버 변수 (클래스 멤버로 선언)
std::vector<NoteEvent> parsedMidiData;

// 가짜 MIDI 파싱 데이터를 생성하는 초기화 함수 (10손가락 양손 버전)
void initMockMidiData() {
    parsedMidiData.clear();

    // duration_ms를 450.0f로 주어, 음과 음 사이에 살짝 손을 떼는(50ms) 디테일을 추가했습니다.

    // =================================================================
    // [파트 1] 양손 스케일 상행 (0.0초 ~ 2.5초)
    // =================================================================

    // 🖐️ 오른손: C4(도) ~ G4(솔) 상행 (엄지 -> 새끼)
    parsedMidiData.push_back({ 0.0f,    60, 80, 450.0f, 1, 1 }); // C4 - 엄지
    parsedMidiData.push_back({ 500.0f,  62, 85, 450.0f, 1, 2 }); // D4 - 검지
    parsedMidiData.push_back({ 1000.0f, 64, 80, 450.0f, 1, 3 }); // E4 - 중지
    parsedMidiData.push_back({ 1500.0f, 65, 80, 450.0f, 1, 4 }); // F4 - 약지
    parsedMidiData.push_back({ 2000.0f, 67, 85, 450.0f, 1, 5 }); // G4 - 새끼

    // 🤚 왼손: C3(낮은 도) ~ G3(낮은 솔) 상행 (새끼 -> 엄지)
    // 주의: 피아노에서 왼손은 새끼손가락(5번)이 가장 낮은 음을 칩니다!
    parsedMidiData.push_back({ 0.0f,    48, 80, 450.0f, 0, 5 }); // C3 - 새끼
    parsedMidiData.push_back({ 500.0f,  50, 85, 450.0f, 0, 4 }); // D3 - 약지
    parsedMidiData.push_back({ 1000.0f, 52, 80, 450.0f, 0, 3 }); // E3 - 중지
    parsedMidiData.push_back({ 1500.0f, 53, 80, 450.0f, 0, 2 }); // F3 - 검지
    parsedMidiData.push_back({ 2000.0f, 55, 85, 450.0f, 0, 1 }); // G3 - 엄지


    // =================================================================
    // [파트 2] 양손 웅장한 C Major 화음 동시 타건 (3.0초 ~ 4.5초)
    // =================================================================

    // 🤚 왼손 C3, E3, G3 (새끼, 중지, 엄지)
    parsedMidiData.push_back({ 3000.0f, 48, 90, 1500.0f, 0, 5 });
    parsedMidiData.push_back({ 3000.0f, 52, 90, 1500.0f, 0, 3 });
    parsedMidiData.push_back({ 3000.0f, 55, 90, 1500.0f, 0, 1 });

    // 🖐️ 오른손 C4, E4, G4 (엄지, 중지, 새끼)
    parsedMidiData.push_back({ 3000.0f, 60, 90, 1500.0f, 1, 1 });
    parsedMidiData.push_back({ 3000.0f, 64, 90, 1500.0f, 1, 3 });
    parsedMidiData.push_back({ 3000.0f, 67, 90, 1500.0f, 1, 5 });
}

// 2. 현재 시뮬레이션 시간에 맞춰 활성화된(눌려있는) 노트만 걸러내는 함수
std::vector<NoteEvent> getActiveNotesForCurrentTime(float currentTimeSec) {
    std::vector<NoteEvent> activeNotes;

    // 현재 시간을 밀리초(ms)로 변환 (루프 테스트를 위해 6초 단위로 반복되게 설정)
    float loopTimeSec = std::fmod(currentTimeSec, 6.0f);
    float currentTimeMs = loopTimeSec * 1000.0f;

    for (const auto& note : parsedMidiData) {
        // 노트의 시작 시간 <= 현재 시간 <= 노트의 종료 시간(시작 + 지속시간)
        if (currentTimeMs >= note.time_ms && currentTimeMs <= (note.time_ms + note.duration_ms)) {
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
        initMockMidiData();
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

    VkCommandPool commandPool;

    std::vector<Joint> joints;
	std::vector<Finger> hand;
    std::vector<Vertex> vertices;

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
                    // [엄지]
                    hand[i].joints[0].limits = deg2rad(50.0f, 50.0f, -40.0f, 40.0f, 0.0f, 15.0f);
                    hand[i].joints[1].limits = deg2rad(60.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[2].limits = deg2rad(80.0f, 5.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[3].limits = deg2rad(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].rootOffset = glm::vec3(0.0f, -0.2f, zOff);
                }
                else {
                    // [일반 손가락]
                    hand[i].joints[0].limits = deg2rad(90.0f, 20.0f, -20.0f, 20.0f, 0.0f, 0.0f);
                    hand[i].joints[1].limits = deg2rad(100.0f, 10.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[2].limits = deg2rad(80.0f, 5.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].joints[3].limits = deg2rad(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
                    hand[i].rootOffset = glm::vec3(0.0f, 0.0f, zOff);
                }
            }
        }
        vertices.resize(80);
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

        vkCmdBindPipeline(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, graphicsPipeline);


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
        ubo.view = glm::lookAt(
            glm::vec3(-3.5f, 3.0f, 0.0f),  // 카메라 위치 (Eye): X축 뒤쪽, Y축 위쪽
            glm::vec3(1.0f, 0.0f, 0.0f),   // 바라보는 곳 (Center): 손가락들이 뻗어있는 중심
            glm::vec3(0.0f, 1.0f, 0.0f)    // 위쪽 방향 (Up)
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
        // 1. 시간에 따른 C코드와 F코드 블렌딩 비율 계산 (0.0 ~ 1.0 반복)
        // 이 t 값은 타겟 이동뿐만 아니라 베지어 곡선의 매개변수로도 사용됩니다.
        float t = (std::sin(time * 3.141592f) + 1.0f) * 0.5f;

        // --- [손목 트래킹 로직 (포물선 움직임 추가)] ---
        static glm::vec3 targetLeftWrist = glm::vec3(0.0f, 0.3f, -1.2f);
        static glm::vec3 targetRightWrist = glm::vec3(0.0f, 0.3f, 1.2f);

        float leftZSum = 0.0f, rightZSum = 0.0f;
        int leftCount = 0, rightCount = 0;

        for (const auto& note : activeNotes) {
            glm::vec3 keyPos = getKeyPosition(note.pitch);
            if (note.hand == 0) { leftZSum += keyPos.z; leftCount++; }
            else { rightZSum += keyPos.z; rightCount++; }
        }

        if (leftCount > 0) targetLeftWrist.z = (leftZSum / leftCount);
        if (rightCount > 0) targetRightWrist.z = (rightZSum / rightCount);

        static glm::vec3 currentLeftWrist = targetLeftWrist;
        static glm::vec3 currentRightWrist = targetRightWrist;

        // 1. Z축(좌우) 이동 보간
        float wristLerpSpeed = 0.12f;
        currentLeftWrist.z = glm::mix(currentLeftWrist.z, targetLeftWrist.z, wristLerpSpeed);
        currentRightWrist.z = glm::mix(currentRightWrist.z, targetRightWrist.z, wristLerpSpeed);

        // 2. Y축(상하) 아치형 곡선 추가: 타겟과의 거리가 멀수록 손목을 위로 들어올림
        float baseWristY = 0.3f;
        float arcMultiplier = 0.2f; // 손목이 들리는 높이 가중치
        float targetY_L = baseWristY + std::abs(targetLeftWrist.z - currentLeftWrist.z) * arcMultiplier;
        float targetY_R = baseWristY + std::abs(targetRightWrist.z - currentRightWrist.z) * arcMultiplier;

        currentLeftWrist.y = glm::mix(currentLeftWrist.y, targetY_L, 0.15f);
        currentRightWrist.y = glm::mix(currentRightWrist.y, targetY_R, 0.15f);


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

        // 1. 시간에 따른 C코드와 F코드 블렌딩 비율 계산 (0.0 ~ 1.0 반복)
        // 사인 함수를 사용하여 부드럽게 두 코드를 오가도록 만듭니다. (주기: 약 2초)
        float blend = (std::sin(time * 3.141592f) + 1.0f) * 0.5f;

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

        // 1. 대기 상태 위치 설정
        float restX = 1.0f;
        float restY = -0.1f;
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
            
            for (int i = 0; i < 3; i++) {
                hand[fingerIdx].joints[i].angle *= 0.98f;
            }

            int iterationLimit = 15;
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

                // 3. dTheta 적용 (W^-1 * J^T * e_star)
                dofIndex = 0;
                for (int i = 0; i < 3; i++) {
                    glm::vec3 dTheta(
                        W_inv[dofIndex] * glm::dot(J_cols[dofIndex], e_star),
                        W_inv[dofIndex + 1] * glm::dot(J_cols[dofIndex + 1], e_star),
                        W_inv[dofIndex + 2] * glm::dot(J_cols[dofIndex + 2], e_star)
                    );

                    float maxStep = 0.1f;
                    float stepLen = glm::length(dTheta);
                    if (stepLen > maxStep) {
                        dTheta *= (maxStep / stepLen); // 방향은 유지하고 최대 길이만 제한
                    }

                    hand[fingerIdx].joints[i].angle += dTheta;
                    dofIndex += 3;

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
